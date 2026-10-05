import copy
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_past_stats
from app.models import Player, PlayerExternalId, PlayerSeasonStats
from app.sources.players.base import name_key
from app.sources.players.nba_stats import NbaStats

FIXTURES = Path(__file__).parent / "fixtures"
SEASONS = ["2024-25", "2025-26"]
JOKIC, FLAGG = "203999", "1642843"


@pytest.fixture(scope="module")
def raw() -> dict:
    # stats.nba.com leaguedashplayerstats totals, 2024-25 and 2025-26, columns trimmed.
    return json.loads(gzip.decompress((FIXTURES / "nba_stats.json.gz").read_bytes()))


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def _player(db, first, last, team, nba_id=None) -> Player:
    p = Player(first_name=first, last_name=last, name_key=name_key(first, last), team=team,
               position=None, identity_source="yahoo", updated_at=datetime.now(UTC))
    db.add(p)
    db.flush()
    if nba_id:
        db.add(PlayerExternalId(player_pk=p.id, source="nba", external_id=nba_id))
    return p


def test_parse(raw):
    players = {p.external_id: p for p in NbaStats().parse(raw)}
    assert len(players) > 600
    jokic = players[JOKIC]
    assert (jokic.first_name, jokic.last_name, jokic.team) == ("Nikola", "Jokić", "DEN")
    assert [line.season for line in jokic.actual] == SEASONS
    s = jokic.actual[0].stats
    assert s == {"gp": 70, "fgm": 786, "fga": 1364, "ftm": 361, "fta": 451, "tpm": 138,
                 "pts": 2071, "reb": 893, "ast": 716, "stl": 127, "blk": 45, "tov": 230}
    assert s["pts"] == 2 * s["fgm"] + s["tpm"] + s["ftm"]
    assert [line.season for line in players[FLAGG].actual] == ["2025-26"]  # rookie in 2025-26


def test_parse_rejects_bad_payloads(raw):
    dup = copy.deepcopy(raw)
    rows = dup["2025-26"]["resultSets"][0]["rowSet"]
    rows.append(rows[0])
    with pytest.raises(ValueError, match="more than one row"):
        NbaStats().parse(dup)
    short = copy.deepcopy(raw)
    del short["2025-26"]["resultSets"][0]["rowSet"][10:]
    with pytest.raises(ValueError, match="only 10 rows"):
        NbaStats().parse(short)
    with pytest.raises(ValueError, match="asked 2023-24"):
        NbaStats().parse({"2023-24": raw["2024-25"]})


def test_default_seasons():
    assert sync_past_stats.default_seasons("2026-27") == ["2022-23", "2023-24", "2024-25", "2025-26"]


def test_write_links_existing_players_only(db, raw):
    jokic = _player(db, "Nikola", "Jokic", "DEN", nba_id=JOKIC)
    flagg = _player(db, "Cooper", "Flagg", "DAL")  # no NBA id yet: name match
    players = NbaStats().parse(raw)
    for _ in range(2):  # idempotent
        report = sync_past_stats.write(db, players, SEASONS, links={})
        db.flush()
    assert report.rows == {"2024-25": 1, "2025-26": 2}
    assert report.skipped["2025-26"] == len(raw["2025-26"]["resultSets"][0]["rowSet"]) - 2
    assert db.scalar(select(func.count(Player.id))) == 2  # no players created
    assert db.scalar(select(func.count(PlayerSeasonStats.id))) == 3
    assert db.scalar(select(PlayerExternalId.external_id).where(
        PlayerExternalId.player_pk == flagg.id, PlayerExternalId.source == "nba")) == FLAGG
    assert (jokic.first_name, jokic.last_name) == ("Nikola", "Jokic")  # identity untouched
    gp = db.scalar(select(PlayerSeasonStats.gp).where(
        PlayerSeasonStats.player_pk == flagg.id, PlayerSeasonStats.season == "2025-26"))
    assert gp == 70


def test_write_keeps_other_seasons(db, raw):
    p = _player(db, "Nikola", "Jokic", "DEN", nba_id=JOKIC)
    players = NbaStats().parse(raw)
    sync_past_stats.write(db, players, SEASONS, links={})
    sync_past_stats.write(db, players, ["2025-26"], links={})
    db.flush()
    seasons = db.scalars(select(PlayerSeasonStats.season).where(PlayerSeasonStats.player_pk == p.id))
    assert sorted(seasons) == SEASONS
