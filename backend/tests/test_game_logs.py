import copy
import gzip
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_game_logs
from app.models import Player, PlayerExternalId, PlayerGameLog
from app.sources.players import nba_gamelog
from app.sources.players.base import name_key
from app.sources.players.nba_gamelog import NbaGameLog
from app.sources.players.nba_stats import NbaStats

FIXTURES = Path(__file__).parent / "fixtures"
JOKIC, FLAGG, TRADED = "203999", "1642843", "1629216"


def _load(name: str) -> dict:
    return json.loads(gzip.decompress((FIXTURES / name).read_bytes()))


@pytest.fixture
def raw(monkeypatch) -> dict:
    # leaguegamelog 2025-26, rows of 3 players only, columns trimmed.
    monkeypatch.setattr(nba_gamelog, "MIN_ROWS", 1)
    return _load("nba_gamelog.json.gz")


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_parse(raw):
    players = {sp.external_id: (sp, games) for sp, games in NbaGameLog().parse(raw)}
    assert set(players) == {JOKIC, FLAGG, TRADED}
    sp, games = players[JOKIC]
    assert (sp.first_name, sp.last_name, sp.team) == ("Nikola", "Jokić", "DEN")
    assert all(g.team == "DEN" and g.opponent and g.opponent != "DEN" for g in games)
    assert {g.home for g in games} == {True, False}
    assert games == sorted(games, key=lambda g: g.game_date)
    assert all(g.stats["pts"] == 2 * g.stats["fgm"] + g.stats["tpm"] + g.stats["ftm"] for g in games)
    # a traded player keeps the team of each game; the player's team is the last one
    sp, games = players[TRADED]
    assert len({g.team for g in games}) == 2 and sp.team == games[-1].team


def test_games_add_up_to_season_totals(raw):
    """Same stats.nba.com data, two endpoints: game logs must sum to the season totals."""
    totals = {sp.external_id: sp.actual for sp in NbaStats().parse(_load("nba_stats.json.gz"))}
    for sp, games in NbaGameLog().parse(raw):
        line = next(x for x in totals[sp.external_id] if x.season == "2025-26").stats
        summed = defaultdict(float)
        for g in games:
            for k, v in g.stats.items():
                summed[k] += v
        assert len(games) == line["gp"], sp.last_name
        assert {k: summed[k] for k in line if k != "gp"} == {k: v for k, v in line.items() if k != "gp"}


def test_parse_rejects_bad_payloads(raw, monkeypatch):
    dup = copy.deepcopy(raw)
    rows = dup["2025-26"]["resultSets"][0]["rowSet"]
    rows.append(rows[0])
    with pytest.raises(ValueError, match="twice in game"):
        NbaGameLog().parse(dup)
    with pytest.raises(ValueError, match="asked 2024-25"):
        NbaGameLog().parse({"2024-25": raw["2025-26"]})
    monkeypatch.setattr(nba_gamelog, "MIN_ROWS", 20000)
    with pytest.raises(ValueError, match="only"):
        NbaGameLog().parse(raw)


def test_write_links_existing_players_only(db, raw):
    p = Player(first_name="Nikola", last_name="Jokic", name_key=name_key("Nikola", "Jokic"),
               team="DEN", position=None, identity_source="yahoo", updated_at=datetime.now(UTC))
    db.add(p)
    db.flush()
    players = NbaGameLog().parse(raw)
    n_jokic = len(next(g for sp, g in players if sp.external_id == JOKIC))
    for _ in range(2):  # idempotent
        report = sync_game_logs.write(db, players, ["2025-26"], links={})
        db.flush()
    assert report.rows == {"2025-26": n_jokic}
    assert report.skipped["2025-26"] == len(raw["2025-26"]["resultSets"][0]["rowSet"]) - n_jokic
    assert db.scalar(select(func.count(Player.id))) == 1
    assert db.scalar(select(func.count(PlayerGameLog.id))) == n_jokic
    assert db.scalar(select(PlayerExternalId.external_id).where(
        PlayerExternalId.player_pk == p.id, PlayerExternalId.source == "nba")) == JOKIC
    first = db.scalars(select(PlayerGameLog).order_by(PlayerGameLog.game_date)).first()
    assert first.season == "2025-26" and first.game_date >= date(2025, 10, 1)


def test_preseason_rows_kept_apart(db, raw):
    """Preseason and regular season rows of one season: each sync replaces only its own type."""
    db.add(Player(first_name="Nikola", last_name="Jokic", name_key=name_key("Nikola", "Jokic"),
                  team="DEN", position=None, identity_source="yahoo", updated_at=datetime.now(UTC)))
    db.flush()
    regular = NbaGameLog().parse(raw)
    pre = copy.deepcopy(regular)
    for _, games in pre:
        for g in games:
            g.game_id = "001" + g.game_id[3:]  # preseason ids start with 001
    sync_game_logs.write(db, regular, ["2025-26"], links={})
    sync_game_logs.write(db, pre, ["2025-26"], links={}, season_type="preseason")
    sync_game_logs.write(db, regular, ["2025-26"], links={})  # must not delete preseason rows
    db.flush()
    counts = dict(db.execute(select(PlayerGameLog.season_type, func.count())
                             .group_by(PlayerGameLog.season_type)).all())
    assert counts["regular"] == counts["preseason"] > 0
