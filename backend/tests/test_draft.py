import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from app.db import init_db
from app.draft import capture
from app.draft.parser import (
    AutopickOn, Bid, Budgets, Nomination, OnTheClock, PastPicks, Presence, Sale, Unknown,
    parse_capture_line, parse_ws,
)
from app.draft.state import replay
from app.jobs.ingest_draft import ingest
from app.models import Draft, DraftPick, DraftTeam

FIXTURE = Path(__file__).parent / "fixtures" / "draft_capture_mock_2600009.jsonl.gz"
LEAGUE = "2600009"


@pytest.fixture(scope="module")
def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="module")
def state(rows):
    return replay(te for te in map(parse_capture_line, rows) if te)


@pytest.fixture
def capture_dir(tmp_path):
    (tmp_path / LEAGUE).mkdir()
    shutil.copy(FIXTURE, tmp_path / LEAGUE / FIXTURE.name)
    return tmp_path


def test_parse_messages():
    assert parse_ws("D|1|9|30") == OnTheClock(1, 9, 30)
    assert parse_ws("n|9|5352|1|20") == Nomination(9, "5352", 1, 20)
    assert parse_ws("b|6|5352|72|19") == Bid(6, "5352", 72, 19)
    assert parse_ws("0|1|5352|2|C|76") == Sale(1, "5352", 2, "C", 76)
    assert parse_ws("$|12=200|1=150") == Budgets({12: 200, 1: 150})
    assert parse_ws("P|1=5352,2,76|2=10290,10,18") == PastPicks({1: ("5352", 2, 76), 2: ("10290", 10, 18)})
    assert parse_ws("P") == PastPicks({})
    assert parse_ws("A|12=1|11=0") == Presence({12: True, 11: False})
    assert parse_ws("5|3") == AutopickOn(3)
    assert parse_ws("C|9") == Unknown("C", "C|9")
    assert parse_ws("D|x") == Unknown("D", "D|x")  # malformed known type stays raw


def test_replay_fixture_picks(state):
    assert sorted(state.picks) == list(range(1, 77))
    assert state.warnings == []
    assert state.budget == 200
    # Pick 14 was sold while the socket was down (17:52). Only the `P|` replay has it.
    assert [p.pick_no for p in state.picks.values() if p.sold_at is None] == [14]
    assert state.picks[14].roster_slot is None
    # Pick 15 was open at the reconnect: nominator comes from the `D|` after the `b|` snapshot.
    assert state.picks[15].nominating_team_id == 8


def test_replay_fixture_budgets_match_server(rows, state):
    events = [te for te in map(parse_capture_line, rows) if te]
    budget_msgs = [te for te in events if isinstance(te.event, Budgets)]
    assert len(budget_msgs) == 2
    # Replay up to and including the second `$|`: computed money must equal the server's.
    cut = events.index(budget_msgs[-1])
    partial = replay(events[: cut + 1])
    assert partial.warnings == []
    assert {t: partial.money_left(t) for t in partial.server_budgets} == partial.server_budgets


def test_sale_price_equals_last_bid(rows):
    last = {}
    for te in (te for te in map(parse_capture_line, rows) if te):
        e = te.event
        if isinstance(e, (Nomination, Bid)):
            last[e.player_id] = (e.team_id, e.amount)
        elif isinstance(e, Sale):
            assert last[e.player_id] == (e.team_id, e.price)


def test_replay_fixture_live_state(state):
    # The capture ends during a nomination: 77 `D` messages, 76 picks.
    assert state.on_the_clock is not None and state.on_the_clock.pick_no == 77
    assert state.nomination_order == (9, 5, 8, 1, 3, 10, 4, 7, 12, 6, 11, 2)
    assert {1, 3, 4, 8, 9} <= state.autopick
    assert set(state.unknown) <= {"C", "H", "Q", "w", "scout"}


def test_ingest_is_idempotent(capture_dir, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    for _ in range(2):
        with Session(engine) as db, db.begin():
            draft, _ = ingest(db, LEAGUE, capture_dir)
    with Session(engine) as db:
        d = db.scalar(select(Draft))
        assert (d.kind, d.my_team_id, d.budget) == ("mock", 5, 200)
        assert db.scalar(select(func.count()).select_from(Draft)) == 1
        assert db.scalar(select(func.count()).select_from(DraftPick)) == 76
        assert db.scalar(select(func.count()).select_from(DraftTeam)) == 12
        first = db.scalar(select(DraftPick).where(DraftPick.pick_no == 1))
        assert (first.yahoo_player_id, first.team_id, first.price, first.nominating_team_id) == ("5352", 2, 76, 9)


def test_init_db_stamps_pre_alembic_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # schema as create_all made it before Alembic
        conn.execute(text("CREATE TABLE leagues (id INTEGER PRIMARY KEY, league_id VARCHAR)"))
        conn.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY, league_pk INTEGER)"))
        conn.execute(text("INSERT INTO leagues (league_id) VALUES ('23772')"))
    init_db(engine)
    init_db(engine)  # second run is a no-op
    with engine.connect() as conn:
        assert {"drafts", "draft_picks", "draft_teams", "alembic_version"} <= set(inspect(conn).get_table_names())
        assert conn.execute(text("SELECT league_id FROM leagues")).scalar() == "23772"


def test_capture_routes_by_league(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr(capture, "CAPTURE_DIR", tmp_path)
    client = TestClient(app)
    room = "https://basketball.fantasysports.yahoo.com/draftclient/nba/2600123/7?auth="
    client.post("/api/capture", json={"kind": "ws_message", "url": room, "data": {"body": "C|9"}})
    client.post("/api/capture", json={"kind": "fetch", "url": "https://example.com/", "data": {}})
    day = f"{datetime.now(UTC):%Y%m%d}.jsonl"
    assert (tmp_path / "2600123" / day).exists()
    assert (tmp_path / "unknown" / day).exists()
    assert capture.league_ids(tmp_path) == ["2600123"]
    assert capture.page_ids(room) == ("2600123", 7)


def test_init_db_stamps_create_all_db_at_head(tmp_path):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.db import ALEMBIC_INI, Base

    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    engine = create_engine(f"sqlite:///{tmp_path / 'full.db'}")
    Base.metadata.create_all(engine)  # every current table, no alembic_version
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
