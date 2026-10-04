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
    AutopickOff, AutopickOn, Bid, Budgets, Nomination, OnTheClock, PastPicks, Presence, Sale, Unknown,
    parse_capture_line, parse_ws,
)
from app.draft.state import replay
from app.jobs.ingest_draft import ingest
from app.models import Draft, DraftPick, DraftTeam

FIXTURE = Path(__file__).parent / "fixtures" / "draft_capture_mock_2600009.jsonl.gz"
# Second mock (2026-10-04). The user is team 8 and went on autopick, then turned it off.
FIXTURE_2 = Path(__file__).parent / "fixtures" / "draft_capture_mock_2600536.jsonl.gz"
LEAGUE = "2600009"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="module")
def rows():
    return _rows(FIXTURE)


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


@pytest.mark.parametrize("path", [FIXTURE, FIXTURE_2], ids=["2600009", "2600536"])
def test_sale_price_equals_last_bid(path):
    last = {}
    for te in (te for te in map(parse_capture_line, _rows(path)) if te):
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


def test_replay_second_mock_autopick_on_off():
    events = [te for te in map(parse_capture_line, _rows(FIXTURE_2)) if te]
    state = replay(events)
    assert state.warnings == []
    assert sorted(state.picks) == list(range(1, 42))
    # Team 8 (the user): `5|8` at the 01:30 timeout, `6|8` at 01:37:19 when the user turned autopick off.
    first_off = next(i for i, te in enumerate(events) if te.event == AutopickOff(8))
    assert 8 in replay(events[:first_off]).autopick
    assert 8 not in replay(events[: first_off + 1]).autopick
    assert {1, 5} <= state.autopick
    # `X|29` came only before the user's own timeouts (2 of 2), never before other teams' (`5|5`, `5|1`).
    assert state.unknown.get("X") == 2


def _post_all(client, rows):
    for row in rows:
        row = {k: v for k, v in row.items() if k != "received_at"}
        assert client.post("/api/capture", json=row).status_code == 200


def test_live_feed_matches_replay(tmp_path, monkeypatch, rows, state):
    from app.api import capture as capture_api
    from app.draft import live
    from app.main import app

    monkeypatch.setattr(capture, "CAPTURE_DIR", tmp_path)
    written = []
    monkeypatch.setattr(capture_api.ingest_draft, "ingest_now", lambda lid, base: written.append(lid))
    live.reset()
    client = TestClient(app)
    _post_all(client, rows)

    body = client.get(f"/api/draft/live/{LEAGUE}").json()
    assert [p["pick_no"] for p in body["picks"]] == sorted(state.picks)
    assert {(p["player_id"], p["team_id"], p["price"]) for p in body["picks"]} == {
        (p.player_id, p.team_id, p.price) for p in state.picks.values()
    }
    assert {t["team_id"]: t["money_left"] for t in body["teams"]} == {
        t: state.money_left(t) for t in state.server_budgets
    }
    assert body["warnings"] == state.warnings
    assert body["my_team_id"] == 5 and body["kind"] == "mock"
    assert all(t["name"] for t in body["teams"])
    # One DB write per live sale. The first row of the league triggers a load, not a feed.
    assert written == [LEAGUE] * sum(1 for r in rows[1:] if r.get("data", {}).get("body", "").startswith("0|"))
    assert client.get("/api/draft/live").json()[0]["league_id"] == LEAGUE

    # Backend restart: state is rebuilt from the files and is the same.
    live.reset()
    assert client.get(f"/api/draft/live/{LEAGUE}").json()["picks"] == body["picks"]
    assert client.get("/api/draft/live/999").status_code == 404
    live.reset()


def test_live_last_event_counts_countdown(tmp_path, monkeypatch):
    from app.draft import live

    monkeypatch.setattr(capture, "CAPTURE_DIR", tmp_path)
    live.reset()
    room = "https://basketball.fantasysports.yahoo.com/draftclient/nba/2600123/7"
    first = {"kind": "ws_message", "url": room, "received_at": "2026-10-04T01:00:00+00:00", "data": {"body": "I|7|1"}}
    tick = {"kind": "ws_message", "url": room, "received_at": "2026-10-04T01:00:06+00:00", "data": {"body": "C|9"}}
    capture.file_for(first, tmp_path).write_text(json.dumps(first) + "\n")
    assert live.feed(first) is None
    assert live.feed(tick) is None
    d = live.get("2600123")
    assert d.my_team_id == 7 and d.state.nomination_order == (7, 1)
    assert d.last_event_at == datetime(2026, 10, 4, 1, 0, 6, tzinfo=UTC)
    live.reset()
