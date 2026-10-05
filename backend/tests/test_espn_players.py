import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_players
from app.models import Player, PlayerMarketValue, PlayerProjection
from app.sources.players import SOURCES, espn
from app.sources.players.base import name_key
from app.sources.players.espn import EspnPlayers

FIXTURES = Path(__file__).parent / "fixtures"
SEASON = "2026-27"


@pytest.fixture
def players(monkeypatch) -> dict:
    # kona_player_info, 8 players, per-game blocks removed; proTeams trimmed to id and abbrev.
    monkeypatch.setattr(espn, "MIN_PLAYERS", 1)
    raw = json.loads(gzip.decompress((FIXTURES / "espn_players.json.gz").read_bytes()))
    return {f"{p.first_name} {p.last_name}": p for p in EspnPlayers().parse(raw, SEASON)}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_parse(players):
    # Ryan Conwell: no projection, no ROTO rank, no average price -> left out
    assert set(players) == {"Nikola Jokic", "Luka Doncic", "Anthony Davis", "LeBron James",
                            "Klay Thompson", "Jordan Miller", "Chris Paul"}
    j = players["Nikola Jokic"]
    assert (j.team, j.position) == ("DEN", "C")
    assert j.projection.season == SEASON
    assert j.projection.stats == {"gp": 72, "fgm": 762, "fga": 1325, "ftm": 388, "fta": 475,
                                  "tpm": 122, "pts": 2034, "reb": 914, "ast": 727, "stl": 115,
                                  "blk": 58, "tov": 245, "min": 2563.2}
    # last season's preseason projection, kept as a 2025-26 projection
    [past] = j.past_projections
    assert past.season == "2025-26"
    assert (past.stats["gp"], past.stats["pts"], past.stats["min"]) == (74, 2144, 2693.6)
    m = j.market
    assert (m.auction_value, m.average_cost, m.average_pick, m.rank) == (68, 81.83, 1.57, 1)
    assert m.extra["standard_rank"] == 1 and m.extra["outlook"].startswith("Jokic")
    assert m.injury is None


def test_positions_and_free_agents(players):
    assert players["Luka Doncic"].market.positions == ["G"]
    assert players["Anthony Davis"].market.positions == ["F", "C"]  # PF, C; combo slots ignored
    assert players["LeBron James"].market.positions == ["F"]
    assert players["Chris Paul"].team is None  # ESPN proTeamId 0 = FA


def test_projection_stat_ids_hold(players):
    lines = [p.projection.stats for p in players.values() if p.projection]
    assert len(lines) >= 5
    for s in lines:  # FT% is rounded by ESPN, so only PTS is exact
        assert s["pts"] == 2 * s["fgm"] + s["tpm"] + s["ftm"]
        assert s["fgm"] <= s["fga"] and s["ftm"] <= s["fta"] and s["tpm"] <= s["fgm"]


def test_projection_without_gp_is_dropped(players):
    assert players["Jordan Miller"].projection is None  # ESPN sends an empty projection block


def test_espn_never_owns_identity_of_known_players(db, players):
    assert list(SOURCES).index("espn") > list(SOURCES).index("yahoo")
    p = Player(first_name="Nikola", last_name="Jokić", name_key=name_key("Nikola", "Jokić"),
               team="DEN", position="C", identity_source="yahoo", updated_at=datetime.now(UTC))
    db.add(p)
    db.flush()
    for _ in range(2):  # idempotent
        report = sync_players.write(db, "espn", list(players.values()), SEASON, links={})
        db.flush()
    assert report.how == {"id": 7}  # second run: all by ESPN id; the first run created 6 rows
    assert p.last_name == "Jokić" and p.identity_source == "yahoo"
    proj = db.scalars(select(PlayerProjection).where(PlayerProjection.source == "espn")).all()
    assert sorted(x.season for x in proj) == sorted(
        [line.season for x in players.values() if x.projection for line in [x.projection]]
        + [line.season for x in players.values() for line in x.past_projections])
    assert {x.season for x in proj} == {"2025-26", "2026-27"}
    jokic = [x for x in proj if x.player_pk == p.id]
    assert {x.season: x.min for x in jokic} == {"2025-26": 2693.6, "2026-27": 2563.2}
    mv = db.scalar(select(PlayerMarketValue).where(
        PlayerMarketValue.player_pk == p.id, PlayerMarketValue.source == "espn"))
    assert mv.average_cost == 81.83
