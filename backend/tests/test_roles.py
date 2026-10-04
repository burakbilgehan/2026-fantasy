"""Role sources (T-026): DARKO, FantasyPros, Hashtag depth charts, Vegas win totals, refresh."""

import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import refresh, sync_roles
from app.models import (
    DepthChartEntry, Player, PlayerExternalId, PlayerMinutesProjection, SyncRun, TeamWinTotal,
)
from app.sources.players.base import name_key
from app.sources.roles import darko, fantasypros, hashtag, vegas

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _html(name: str) -> str:
    return gzip.decompress((FIXTURES / name).read_bytes()).decode()


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def _player(db, first, last, team, nba_id=None) -> Player:
    p = Player(first_name=first, last_name=last, name_key=name_key(first, last), team=team,
               position=None, identity_source="nba", updated_at=NOW)
    db.add(p)
    db.flush()
    if nba_id:
        db.add(PlayerExternalId(player_pk=p.id, source="nba", external_id=nba_id))
    return p


# --- parsers (pages saved 2026-10-04) ---

def test_darko_parse():
    rows = darko.parse(_html("darko_projections.html.gz"))
    assert len(rows) == 530
    jokic = next(r for r in rows if r.nba_id == "203999")
    assert (jokic.name, jokic.team, round(jokic.mpg, 2)) == ("Nikola Jokic", "DEN", 31.66)
    assert jokic.extra["x_fg_pct"] == pytest.approx(0.534094)  # ".534094" in the page
    assert all(r.team for r in rows)
    # negative model minutes are stored as 0; the raw value stays
    neg = [r for r in rows if r.extra["x_minutes"] < 0]
    assert neg and all(r.mpg == 0 for r in neg)


def test_darko_to_json():
    assert darko.to_json('[{a:.5,b:-.25,c:"x:y",d:void 0}]') == '[{"a":0.5,"b":-0.25,"c":"x:y","d":null}]'


def test_fantasypros_parse():
    rows = fantasypros.parse(_html("fantasypros_projections.html.gz"))
    assert len(rows) == 266
    jokic = next(r for r in rows if r.last_name == "Jokic")
    assert (jokic.fp_id, jokic.team, jokic.positions, jokic.gp) == ("2918", "DEN", ["C"], 75)
    assert jokic.mpg == pytest.approx(2714 / 75)
    assert jokic.extra["PTS"] == 2045  # "2,045" in the page
    assert all(r.team for r in rows)  # NOR, PHO, UTH map to NOP, PHX, UTA


def test_hashtag_parse():
    rows = hashtag.parse(_html("hashtag_depth_charts.html.gz"))
    assert len({r.team for r in rows}) == 30
    atl_pg = [r for r in rows if r.team == "ATL" and r.slot == "PG"]
    assert [(r.depth, r.order, r.name) for r in atl_pg] == [(1, 1, "CJ McCollum"), (3, 2, "Kingston Flemings")]
    assert any(r.team == "PHX" for r in rows)  # Hashtag id "team-PHO"
    assert any(r.name == "Hugo González" for r in rows)  # HTML entities decoded
    for team in {r.team for r in rows}:  # every slot has one starter
        for slot in hashtag.SLOTS:
            assert [r.depth for r in rows if r.team == team and r.slot == slot][0] == 1


def test_vegas_parse():
    rows = vegas.parse(_html("vegas_win_totals.html.gz"), "2026-27")
    by_team = {r.team: r for r in rows}
    assert len(by_team) == 30
    assert (by_team["OKC"].wins, by_team["SAC"].wins) == (60.5, 21.5)
    assert (by_team["BKN"].over_odds, by_team["BKN"].under_odds) == (100, -120)
    with pytest.raises(ValueError):
        vegas.parse(_html("vegas_win_totals.html.gz"), "2027-28")


# --- writers ---

def test_write_minutes_link_only(db):
    jokic = _player(db, "Nikola", "Jokić", "DEN", nba_id="203999")
    rows = darko.parse(_html("darko_projections.html.gz"))
    r = sync_roles.write_darko(db, rows, "2026-27", links={})
    assert r.rows == 1 and r.how["id"] == 1 and len(r.unmatched) == 529
    assert db.scalar(select(Player.id).where(Player.id != jokic.id)) is None  # no player created

    fp = fantasypros.parse(_html("fantasypros_projections.html.gz"))
    r = sync_roles.write_fantasypros(db, fp, "2026-27", links={})
    assert r.how["name"] == 1
    rows = {m.source: m for m in db.scalars(select(PlayerMinutesProjection))}
    assert rows["darko"].gp is None and rows["fantasypros"].gp == 75
    # the name match stored the FantasyPros id; a re-run matches by id and replaces rows
    r = sync_roles.write_fantasypros(db, fp, "2026-27", links={})
    assert r.how["id"] == 1
    assert len(db.scalars(select(PlayerMinutesProjection)).all()) == 2


def test_write_hashtag_rematches_after_trade(db):
    p = _player(db, "CJ", "McCollum", "ATL")
    rows = hashtag.parse(_html("hashtag_depth_charts.html.gz"))
    sync_roles.write_hashtag(db, rows, "2026-27", links={})
    assert db.scalar(select(DepthChartEntry.player_pk).where(DepthChartEntry.player_name == "CJ McCollum")) == p.id
    assert db.scalar(select(PlayerExternalId).where(PlayerExternalId.source == "hashtag")) is None
    # same name on another team later: still matched (unique name), rows replaced
    rows = [r for r in rows if r.team != "WAS"]
    for r in rows:
        if r.name == "CJ McCollum":
            r.team = "WAS"
    sync_roles.write_hashtag(db, rows, "2026-27", links={})
    entries = db.scalars(select(DepthChartEntry).where(DepthChartEntry.player_name == "CJ McCollum")).all()
    assert [(e.team, e.player_pk) for e in entries] == [("WAS", p.id)]


def test_write_vegas(db):
    rows = vegas.parse(_html("vegas_win_totals.html.gz"), "2026-27")
    sync_roles.write_vegas(db, rows, "2026-27")
    sync_roles.write_vegas(db, rows, "2026-27")
    assert len(db.scalars(select(TeamWinTotal)).all()) == 30


# --- refresh ---

def _run(ok, started, finished=None):
    return SyncRun(job="x", started_at=started, finished_at=finished or started, ok=ok)


def test_is_stale():
    job = refresh.Job("x", timedelta(hours=6), lambda: "")
    fresh_ok = _run(True, NOW - timedelta(hours=1))
    old_ok = _run(True, NOW - timedelta(hours=7))
    assert refresh.is_stale(job, None, None, NOW)  # never ran
    assert not refresh.is_stale(job, fresh_ok, fresh_ok, NOW)
    assert refresh.is_stale(job, old_ok, old_ok, NOW)
    # a recent failure waits RETRY_AFTER, an old failure retries
    assert not refresh.is_stale(job, _run(False, NOW - timedelta(minutes=10)), old_ok, NOW)
    assert refresh.is_stale(job, _run(False, NOW - timedelta(hours=2)), old_ok, NOW)
    # naive datetimes from SQLite are UTC
    naive = _run(True, (NOW - timedelta(hours=1)).replace(tzinfo=None))
    assert not refresh.is_stale(job, naive, naive, NOW)


def test_run_stale_isolates_failures(monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker

    import app.db

    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    init_db(engine)
    monkeypatch.setattr(app.db, "SessionLocal", sessionmaker(engine, expire_on_commit=False))

    def boom():
        raise RuntimeError("blocked")

    monkeypatch.setattr(refresh, "JOBS", {
        "bad": refresh.Job("bad", timedelta(hours=1), boom),
        "good": refresh.Job("good", timedelta(hours=1), lambda: "done"),
    })
    runs = {r.job: r for r in refresh.run_stale()}
    assert (runs["bad"].ok, runs["good"].ok, runs["good"].message) == (False, True, "done")
    assert "blocked" in runs["bad"].message
    assert refresh.run_stale() == []  # good is fresh, bad waits RETRY_AFTER
    assert {r.job for r in refresh.run_stale(force=True)} == {"bad", "good"}


def test_write_minutes_two_rows_one_player(db):
    _player(db, "Nikola", "Jokić", "DEN", nba_id="203999")
    rows = [r for r in darko.parse(_html("darko_projections.html.gz")) if r.nba_id == "203999"]
    twin = darko.DarkoPlayer(nba_id="999", name="Nikola Jokic", team="DEN", mpg=1.0, extra={})
    # a manual link points a second source id at the same player
    links = {("nba", "999"): ("nba", "203999")}
    r = sync_roles.write_darko(db, rows + [twin], "2026-27", links=links)
    assert r.how["link"] == 1 and r.rows == 1
