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
from app.sources.players import SOURCES, fantrax
from app.sources.players.base import name_key
from app.sources.players.fantrax import FantraxPlayers, split_name

FIXTURES = Path(__file__).parent / "fixtures"
SEASON = "2026-27"


@pytest.fixture
def raw() -> dict:
    # getAdp rows of 6 players and their getPlayerIds entries (2026-10-05).
    return json.loads(gzip.decompress((FIXTURES / "fantrax_adp.json.gz").read_bytes()))


@pytest.fixture
def players(raw, monkeypatch) -> dict:
    monkeypatch.setattr(fantrax, "MIN_PLAYERS", 1)
    return {f"{p.first_name} {p.last_name}": p for p in FantraxPlayers().parse(raw, SEASON)}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_split_name():
    assert split_name("Oubre Jr., Kelly") == ("Kelly", "Oubre Jr.")
    assert split_name("Payton II, Gary") == ("Gary", "Payton II")
    assert split_name("Nene") == ("Nene", "")


def test_parse(players):
    assert set(players) == {"Nikola Jokic", "Jrue Holiday", "Kelly Oubre Jr.", "Gary Payton II",
                            "David Duke", "Tyler Nickel"}
    j = players["Nikola Jokic"]
    assert (j.external_id, j.team, j.position) == ("03e75", "DEN", "C")
    assert j.projection is None
    m = j.market
    assert (m.season, m.average_pick, m.rank, m.positions) == (SEASON, 1.48, None, None)
    assert m.extra == {"primary_pos": "C", "rotowire_id": 3612,
                       "sportradar_id": "f2625432-3903-4f90-9b0b-2e4f63856bb0"}


def test_teams(players):
    assert players["Gary Payton II"].team == "GSW"  # Fantrax "GS"
    assert players["Tyler Nickel"].team == "NYK"  # Fantrax "NY"
    assert players["David Duke"].team is None  # Fantrax "(N/A)"


def test_short_response_is_refused(raw):
    with pytest.raises(ValueError):
        FantraxPlayers().parse(raw, SEASON)  # 6 < MIN_PLAYERS


def test_links_by_name_and_never_owns_identity(db, players):
    assert list(SOURCES)[-2:] == ["fantrax", "fanscout"]
    p = Player(first_name="Kelly", last_name="Oubre Jr.", name_key=name_key("Kelly", "Oubre Jr."),
               team="IND", position="SF", identity_source="yahoo", updated_at=datetime.now(UTC))
    db.add(p)
    db.flush()
    for _ in range(2):  # idempotent
        report = sync_players.write(db, "fantrax", list(players.values()), SEASON, links={})
        db.flush()
    assert report.how == {"id": 6}
    assert p.identity_source == "yahoo"
    mv = db.scalars(select(PlayerMarketValue).where(PlayerMarketValue.source == "fantrax")).all()
    assert len(mv) == 6
    assert next(x.average_pick for x in mv if x.player_pk == p.id) == 228.19
    assert db.scalars(select(PlayerProjection).where(PlayerProjection.source == "fantrax")).all() == []
