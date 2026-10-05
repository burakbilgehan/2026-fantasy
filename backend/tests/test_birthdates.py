"""Player birth dates: ESPN roster parse, age fallback, and the three write passes."""

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_birthdates
from app.models import Player, PlayerAdvancedStats, PlayerExternalId
from app.sources import birthdates
from app.sources.birthdates import EspnBirth
from app.sources.players.base import name_key

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 5, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def _rosters() -> dict:
    return json.loads(gzip.decompress((FIXTURES / "espn_rosters.json.gz").read_bytes()))


def _player(db, first, last, espn_id=None, age=None, season="2025-26") -> Player:
    p = Player(first_name=first, last_name=last, name_key=name_key(first, last), team=None,
               position=None, identity_source="nba", updated_at=NOW)
    db.add(p)
    db.flush()
    if espn_id:
        db.add(PlayerExternalId(player_pk=p.id, source="espn", external_id=espn_id))
    if age is not None:
        db.add(PlayerAdvancedStats(player_pk=p.id, source="nba", season=season, gp=50, usg_pct=None,
                                   ts_pct=None, extra={"age": age}, fetched_at=NOW))
    db.flush()
    return p


# --- parsers (rosters saved 2026-10-05, athletes trimmed to the used fields) ---

def test_parse_rosters():
    rows = birthdates.parse_rosters(_rosters())
    assert len(rows) == 606
    assert all(r.birth_date for r in rows)
    naw = next(r for r in rows if r.espn_id == "4278039")
    assert (naw.first_name, naw.last_name, naw.birth_date) == (
        "Nickeil", "Alexander-Walker", date(1998, 9, 2))


def test_parse_rosters_too_few_teams():
    raw = _rosters()
    raw["rosters"] = dict(list(raw["rosters"].items())[:29])
    with pytest.raises(ValueError, match="teams"):
        birthdates.parse_rosters(raw)


def test_parse_athletes():
    raw = {"3468": {"id": "3468", "firstName": "Russell", "lastName": "Westbrook",
                    "dateOfBirth": "1988-11-12T08:00Z"},
           "1": {"id": "1", "firstName": "No", "lastName": "Date"}}
    rows = birthdates.parse_athletes(raw)
    assert rows[0].birth_date == date(1988, 11, 12)
    assert rows[1].birth_date is None


def test_approx_birth_date():
    # AGE is the age on June 30 of the end year; the estimate is 6 months before that birthday.
    assert birthdates.approx_birth_date("2025-26", 31) == date(1994, 12, 30)  # Jokic: 1995-02-19
    assert birthdates.approx_birth_date("2022-23", 20.0) == date(2002, 12, 30)


# --- write passes ---

def test_write_passes(db):
    by_id = _player(db, "Nickeil", "Alexander-Walker", espn_id="4278039")
    by_name = _player(db, "Nikola", "Jokić")
    twin_a, twin_b = _player(db, "Jalen", "Williams"), _player(db, "Jalen", "Williams")
    other_id = _player(db, "Some", "Body", espn_id="999")  # same name, another ESPN id
    espn_kept = _player(db, "Old", "Timer", espn_id="3468", age=37)
    aged = _player(db, "Age", "Only", age=31)
    rows = [EspnBirth("4278039", "Nickeil", "Alexander-Walker", date(1998, 9, 2)),
            EspnBirth("3112335", "Nikola", "Jokic", date(1995, 2, 19)),
            EspnBirth("1", "Jalen", "Williams", date(2001, 4, 14)),
            EspnBirth("2", "Some", "Body", date(2000, 1, 1)),
            EspnBirth("3", "Not", "Here", date(2000, 1, 1))]
    report = sync_birthdates.Report()
    sync_birthdates.write_espn(db, rows, report)
    db.flush()
    assert (report.by_id, report.by_name, report.unmatched) == (1, 1, 3)
    assert by_id.birth_date == date(1998, 9, 2) and by_id.birth_date_source == "espn"
    assert by_name.birth_date == date(1995, 2, 19)
    assert twin_a.birth_date is None and twin_b.birth_date is None
    assert other_id.birth_date is None

    assert sync_birthdates.missing_espn_ids(db) == ["3468", "999"]
    sync_birthdates.write_espn(db, [EspnBirth("3468", "Old", "Timer", date(1988, 11, 12))],
                               report, by_name=False)
    db.flush()
    assert report.athlete_pages == 1
    assert sync_birthdates.missing_espn_ids(db) == ["999"]

    sync_birthdates.write_nba_age(db, report)
    db.flush()
    assert report.nba_age == 1
    assert espn_kept.birth_date == date(1988, 11, 12) and espn_kept.birth_date_source == "espn"
    assert aged.birth_date == date(1994, 12, 30) and aged.birth_date_source == "nba_age"

    # An exact date later replaces the approximate one.
    db.add(PlayerExternalId(player_pk=aged.id, source="espn", external_id="77"))
    db.flush()
    sync_birthdates.write_espn(db, [EspnBirth("77", "Age", "Only", date(1995, 3, 1))], report)
    db.flush()
    assert aged.birth_date == date(1995, 3, 1) and aged.birth_date_source == "espn"


def test_nba_age_uses_latest_season(db):
    p = _player(db, "Two", "Seasons", age=24, season="2024-25")
    db.add(PlayerAdvancedStats(player_pk=p.id, source="nba", season="2025-26", gp=50, usg_pct=None,
                               ts_pct=None, extra={"age": 25}, fetched_at=NOW))
    db.flush()
    report = sync_birthdates.Report()
    sync_birthdates.write_nba_age(db, report)
    assert p.birth_date == birthdates.approx_birth_date("2025-26", 25)
