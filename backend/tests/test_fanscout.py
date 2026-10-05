import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs import sync_players
from app.models import Player, PlayerExternalId, PlayerProjection
from app.sources.players import SOURCES, fanscout
from app.sources.players.base import name_key
from app.sources.players.fanscout import FanScoutPlayers, compact, team_rows, team_urls

FIXTURES = Path(__file__).parent / "fixtures"
SEASON = "2026-27"


@pytest.fixture
def raw() -> dict:
    # The one flight chunk of /nba-depth-charts/charlotte-hornets that holds the player data
    # (16 players, 2026-10-05), as the page sends it.
    html = gzip.decompress((FIXTURES / "fanscout_team.html.gz").read_bytes()).decode()
    return {"pages": 1, "rows": [compact(r) for r in team_rows(html)]}


@pytest.fixture
def players(raw, monkeypatch) -> dict:
    monkeypatch.setattr(fanscout, "MIN_PROJECTIONS", 1)
    return {f"{p.first_name} {p.last_name}": p for p in FanScoutPlayers().parse(raw, SEASON)}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_team_urls():
    urls = [f"https://fanscout.pro/nba-depth-charts/team-{i}" for i in range(30)]
    xml = "".join(f"<loc>{u}</loc>" for u in urls) + "<loc>https://fanscout.pro/nba-depth-charts</loc>"
    assert team_urls(xml) == sorted(urls)
    with pytest.raises(ValueError):
        team_urls("".join(f"<loc>{u}</loc>" for u in urls[:29]))


def test_parse(players):
    assert len(players) == 16
    k = players["Kon Knueppel"]
    assert (k.external_id, k.team, k.aliases) == ("1642851", "CHA", [("nba", "1642851")])
    s = k.projection.stats
    assert k.projection.season == SEASON
    # Per game x 73 games; minutes per game 32 ("totalMinutes" on the page).
    assert s["gp"] == 73 and s["min"] == 32 * 73
    assert s["pts"] == pytest.approx(19.4313 * 73, abs=0.01)
    assert s["fgm"] == pytest.approx(0.452934 * 14.53739 * 73, abs=0.01)
    assert s["ftm"] == pytest.approx(0.853232 * 3.437478 * 73, abs=0.01)
    # PTS = 2 FGM + FTM + 3PM within rounding of FanScout's own model.
    assert s["pts"] == pytest.approx(2 * s["fgm"] + s["ftm"] + s["tpm"], rel=0.02)
    rookie = players["Hannes Steinbach"]  # 2026 draft: no player page projection, but here
    assert rookie.projection.stats["gp"] == 68


def test_duplicates_and_empty_rows_dropped(raw, monkeypatch):
    monkeypatch.setattr(fanscout, "MIN_PROJECTIONS", 1)
    rows = raw["rows"] + [raw["rows"][0]]  # a player on two pages: the first wins
    rows.append({**raw["rows"][1], "playerId": "1", "projections": {"gamesPlayed": 0}})
    out = FanScoutPlayers().parse({"rows": rows}, SEASON)
    assert len(out) == 16


def test_short_response_is_refused(raw):
    with pytest.raises(ValueError):
        FanScoutPlayers().parse(raw, SEASON)  # 16 < MIN_PROJECTIONS


def _player(db, first, last, team, nba_id=None) -> Player:
    p = Player(first_name=first, last_name=last, name_key=name_key(first, last), team=team,
               position="F", identity_source="nba", updated_at=datetime.now(UTC))
    db.add(p)
    db.flush()
    if nba_id:
        db.add(PlayerExternalId(player_pk=p.id, source="nba", external_id=nba_id))
    return p


def test_links_by_nba_id_and_never_owns_identity(db, players):
    assert list(SOURCES)[-1] == "fanscout"
    # Same NBA id, other spelling: the alias links it although the names differ.
    k = _player(db, "Kon", "Knuppel", "CHA", nba_id="1642851")
    # No NBA id yet: linked by name, and the NBA id is recorded.
    m = _player(db, "Brandon", "Miller", "CHA")
    for _ in range(2):  # idempotent
        report = sync_players.write(db, "fanscout", list(players.values()), SEASON, links={})
        db.flush()
    assert report.how == {"id": 16}
    assert (k.last_name, k.identity_source) == ("Knuppel", "nba")
    ids = {(x.source, x.external_id): x.player_pk for x in db.scalars(select(PlayerExternalId))}
    assert ids[("fanscout", "1642851")] == k.id
    assert ids[("nba", "1641706")] == ids[("fanscout", "1641706")] == m.id
    assert sum(1 for s, _ in ids if s == "nba") == 16  # 14 new rows got their NBA id too
    proj = db.scalars(select(PlayerProjection).where(PlayerProjection.source == "fanscout")).all()
    assert len(proj) == 16
    assert next(p.gp for p in proj if p.player_pk == k.id) == 73


def test_first_run_match_kinds(db, players):
    _player(db, "Kon", "Knuppel", "CHA", nba_id="1642851")
    _player(db, "Brandon", "Miller", "CHA")
    report = sync_players.write(db, "fanscout", list(players.values()), SEASON, links={})
    assert report.how == {"alias": 1, "name": 1, "new": 14}
