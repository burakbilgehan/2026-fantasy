import gzip
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_players, sync_schedule
from app.models import (
    NbaGame, Player, PlayerExternalId, PlayerMarketValue, PlayerProjection, PlayerSeasonStats,
)
from app.sources.players.base import name_key
from app.sources.players.nba_index import NbaIndex
from app.sources.players.yahoo_pubapi import YahooPlayers
from app.sources.schedule import espn
from app.sources.teams import NBA_TEAMS, canonical

FIXTURES = Path(__file__).parent / "fixtures"
SEASON = "2026-27"


def _read(name: str) -> str:
    return gzip.decompress((FIXTURES / name).read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def yahoo_raw() -> dict:
    return json.loads(_read("yahoo_players.json.gz"))


@pytest.fixture(scope="module")
def nba_raw() -> str:
    return _read("nba_players.html.gz")


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def _by_last(players, last):
    return next(p for p in players if p.last_name == last and p.first_name != "Bronny")


def test_name_key():
    assert name_key("Jonas", "Valančiūnas") == "jonas valanciunas"
    assert name_key("Jameer", "Nelson Jr.") == "jameer nelson"
    assert name_key("D'Angelo", "Russell") == "dangelo russell"
    assert name_key("Nigel", "Hayes-Davis") == "nigel hayes davis"


def test_canonical_teams():
    assert {canonical(a) for a in ("GS", "NY", "NO", "SA", "UTAH", "WSH")} == {
        "GSW", "NYK", "NOP", "SAS", "UTA", "WAS"}
    assert canonical("FA") is None and canonical("") is None
    assert all(canonical(t) == t for t in NBA_TEAMS)


def test_yahoo_parse(yahoo_raw):
    players = YahooPlayers("23772").parse(yahoo_raw, SEASON)
    lebron = _by_last(players, "James")
    assert lebron.external_id == "3704" and lebron.team == "PHI"
    assert lebron.projection.season == "2026-27"
    assert lebron.projection.stats == {
        "gp": 66, "fga": 934, "fgm": 482, "fta": 287, "ftm": 218, "tpm": 94,
        "pts": 1276, "reb": 385, "ast": 432, "stl": 63, "blk": 31, "tov": 185,
    }
    assert [a.season for a in lebron.actual] == ["2025-26"]
    assert lebron.market.auction_value == 25 and lebron.market.average_cost == 21.4
    # League 23772 feed uses the league's own positions (G, F, C), not PG/SG/SF/PF.
    assert lebron.market.positions == ["F"]
    # Cooper Flagg was drafted in 2025, so season_stats is 2025-26.
    assert _by_last(players, "Flagg").actual[0].stats["gp"] == 70


def test_yahoo_stat_ids_hold(yahoo_raw):
    for p in YahooPlayers("23772").parse(yahoo_raw, SEASON):
        for line in [p.projection, *p.actual]:
            if line:
                s = line.stats
                assert abs(2 * s["fgm"] + s["ftm"] + s["tpm"] - s["pts"]) <= 1
                assert s["fga"] >= s["fgm"] and s["fta"] >= s["ftm"]


def test_yahoo_missing_stats_give_no_line():
    raw = {"service": {"player_list": [{
        "id": 1, "fname": "A", "lname": "B", "team_abbr": "BOS", "pos": [],
        "projected_stats": {k: "-" for k in ("0", "3", "4")}, "season_stats": {},
    }]}}
    p = YahooPlayers("23772").parse(raw, SEASON)[0]
    assert p.projection is None and p.actual == []


def test_nba_parse(nba_raw):
    players = NbaIndex().parse(nba_raw, SEASON)
    assert len(players) == 620
    assert all(p.team in NBA_TEAMS for p in players)
    assert len({p.external_id for p in players}) == 620


def test_nba_parse_rejects_short_page():
    html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"players":[]}}}</script>'
    with pytest.raises(ValueError):
        NbaIndex().parse(html, SEASON)


def test_sync_links_sources_and_is_idempotent(db, yahoo_raw, nba_raw):
    nba, yahoo = NbaIndex().parse(nba_raw, SEASON), YahooPlayers("23772").parse(yahoo_raw, SEASON)
    for _ in range(2):
        r_nba = sync_players.write(db, "nba", nba, SEASON, links={})
        r_y = sync_players.write(db, "yahoo", yahoo, SEASON, links={})
        db.commit()
    assert r_nba.how == {"id": 620} and r_y.how["id"] == len(yahoo)
    nba_keys = {name_key(p.first_name, p.last_name) for p in nba}
    yahoo_only = [p for p in yahoo if name_key(p.first_name, p.last_name) not in nba_keys]
    assert {p.last_name for p in yahoo_only} == {"Westbrook", "Valančiūnas"}  # not on a roster
    assert db.query(Player).count() == 620 + len(yahoo_only)
    assert db.query(PlayerMarketValue).count() == len(yahoo)
    assert db.query(PlayerProjection).count() == sum(1 for p in yahoo if p.projection)
    assert db.query(PlayerSeasonStats).count() == sum(len(p.actual) for p in yahoo)

    jokic = db.scalar(select(Player).where(Player.last_name == "Jokić"))
    ids = {x.source for x in db.scalars(select(PlayerExternalId).where(PlayerExternalId.player_pk == jokic.id))}
    assert ids == {"nba", "yahoo"}
    # NBA.com owns the team: Yahoo says CLE, nba.com says WAS.
    assert db.scalar(select(Player.team).where(Player.last_name == "Livingston")) == "WAS"


def test_first_sync_by_name_then_team(db):
    from app.sources.players.base import SourcePlayer

    nba = [SourcePlayer("1", "Jalen", "Williams", "OKC"), SourcePlayer("2", "Jalen", "Williams", "DEN")]
    sync_players.write(db, "nba", nba, SEASON, links={})
    r = sync_players.write(db, "yahoo", [
        SourcePlayer("a", "Jalen", "Williams", "DEN"),
        SourcePlayer("b", "Jalen", "Williams", "MIA"),  # traded? cannot tell: new row
    ], SEASON, links={})
    assert r.how == {"name+team": 1, "ambiguous": 1}
    den = db.scalar(select(PlayerExternalId).where(PlayerExternalId.external_id == "a"))
    assert den.player_pk == db.scalar(select(PlayerExternalId.player_pk).where(PlayerExternalId.external_id == "2"))


def test_manual_link(db):
    from app.sources.players.base import SourcePlayer

    sync_players.write(db, "nba", [SourcePlayer("9", "Nicolas", "Claxton", "BKN")], SEASON, links={})
    r = sync_players.write(db, "yahoo", [SourcePlayer("y9", "Nic", "Claxton", "BKN")], SEASON,
                           links={("yahoo", "y9"): ("nba", "9")})
    assert r.how == {"link": 1} and db.query(Player).count() == 1


def test_owner_drops_player_to_free_agent(db):
    from app.sources.players.base import SourcePlayer

    sync_players.write(db, "nba", [SourcePlayer("1", "A", "B", "BOS")], SEASON, links={})
    sync_players.write(db, "nba", [], SEASON, links={})
    assert db.scalar(select(Player.team)) is None


def test_espn_schedule_parse_and_write(db):
    raw = json.loads(_read("espn_schedule.json.gz"))
    assert len(espn.team_ids(raw["teams"])) == 30
    games = espn.parse(raw, SEASON)
    ids = [g.source_game_id for g in games]
    assert len(ids) == len(set(ids)) < 12  # ATL at ORL appears in both team schedules
    first = games[0]
    assert (first.away, first.home) == ("ATL", "ORL")
    # 23:00 UTC on 2026-10-21 is 19:00 ET the same day.
    assert first.game_date_et == date(2026, 10, 21)
    for _ in range(2):
        sync_schedule.write(db, games, SEASON)
        db.commit()
    assert db.query(NbaGame).count() == len(games)


def test_espn_late_utc_game_keeps_et_date():
    raw = {"schedules": {"1": {"events": [{
        "id": "x", "date": "2026-10-22T02:30Z", "season": {"year": 2027}, "seasonType": {"type": 2},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "GS"}},
            {"homeAway": "away", "team": {"abbreviation": "UTAH"}},
        ]}],
    }]}}}
    g = espn.parse(raw, SEASON)[0]
    assert g.game_date_et == date(2026, 10, 21) and (g.home, g.away) == ("GSW", "UTA")


def test_team_only_from_nba():
    """NBA.com is the only team source: another source never sets a team (user, 2026-10-05)."""
    from datetime import UTC, datetime

    from app.jobs.sync_players import _set_identity
    from app.models import Player
    from app.sources.players.base import SourcePlayer

    now = datetime.now(UTC)
    p = Player(identity_source="")
    _set_identity(p, "yahoo", SourcePlayer(external_id="1", first_name="D'Angelo", last_name="Russell", team="MEM"), now)
    assert p.team is None and p.identity_source == "yahoo"
    _set_identity(p, "nba", SourcePlayer(external_id="2", first_name="D'Angelo", last_name="Russell", team="DAL"), now)
    assert p.team == "DAL" and p.identity_source == "nba"
