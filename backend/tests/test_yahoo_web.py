import gzip
from pathlib import Path

from app.sources.yahoo import web

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode("utf-8")


def test_parse_settings():
    s = web.parse_settings(_html("settings"))
    assert s["name"] == "Deh Deh"
    assert s["num_teams"] == 12
    assert s["scoring_type"] == "Head-to-Head - Categories"
    assert s["draft_type"] == "Live Salary Cap Draft"
    assert s["draft_budget"] == 200
    assert s["draft_time"].startswith("Sun Oct 18")
    assert s["roster_positions"] == [
        "G", "G", "G", "F", "F", "F", "C", "Util", "Util", "Util", "BN", "BN", "IL", "IL", "IL", "IL"
    ]
    assert s["stat_categories"] == ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]


def test_parse_teams_keeps_unicode():
    teams = web.parse_teams(_html("league"), "23772")
    assert [t["team_id"] for t in teams] == list(range(1, 13))
    names = {t["team_id"]: t["name"] for t in teams}
    assert names[2] == "Bobcats şehir hastaneleri"
    assert names[6] == "GOA Ta’biat Parki"
    assert names[8] == "Haydar Baş"


def test_league_url():
    assert web.league_url("23772") == "https://basketball.fantasysports.yahoo.com/nba/23772"
    assert web.league_url("38073", 2025) == "https://basketball.fantasysports.yahoo.com/2025/nba/38073"


def test_parse_previous_league():
    assert web.parse_previous_league(_html("league")) == (2025, "38073")
    assert web.parse_previous_league("<html></html>") is None


def test_parse_draft_results():
    picks = web.parse_draft_results(_html("past_draftresults"))
    assert len(picks) == 144
    assert picks[0] == {
        "pick_no": 1, "yahoo_player_id": "5352", "player_name": "Nikola Jokić", "price": 87,
        "team_name": "GOA Ta’biat Parki",
    }
    assert [p["pick_no"] for p in picks] == list(range(1, 145))
    spent: dict[str, int] = {}
    for p in picks:
        spent[p["team_name"]] = spent.get(p["team_name"], 0) + p["price"]
    assert len(spent) == 12
    assert all(v <= 200 for v in spent.values())
    assert spent["Bobcats şehir hastaneleri"] == 186
