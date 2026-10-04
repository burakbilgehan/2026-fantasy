"""Read-only scraper for the public Yahoo league pages.

League 23772 has "Make League Publicly Viewable: Yes", so these pages load
without login (verified 2026-10-03). Fallback while the Fantasy API is gated.
Plain GET only. Every response is cached in data/raw/yahoo_web/.
"""

import re
import time

import httpx
from bs4 import BeautifulSoup

from app.config import RAW_DIR

HOST = "https://basketball.fantasysports.yahoo.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 2026-fantasy personal read-only"
CACHE_DIR = RAW_DIR / "yahoo_web"


def league_url(league_id: str, year: int | None = None) -> str:
    """Past seasons live under a year prefix: /2025/nba/38073/ (verified 2026-10-04)."""
    return f"{HOST}/nba/{league_id}" if year is None else f"{HOST}/{year}/nba/{league_id}"


def fetch(
    league_id: str, page: str = "", http: httpx.Client | None = None, year: int | None = None
) -> str:
    http = http or httpx.Client(timeout=20, follow_redirects=True)
    resp = http.get(f"{league_url(league_id, year)}/{page}", headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    html = resp.content.decode("utf-8")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    name = page.strip("/").replace("/", "_") or "league"
    prefix = league_id if year is None else f"{year}_{league_id}"
    (CACHE_DIR / f"{prefix}_{name}_{int(time.time())}.html").write_text(html, encoding="utf-8")
    return html


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_settings_table(html: str) -> dict[str, str]:
    """Return {label: value} from the 'Scoring & Settings' table."""
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 2:
            continue
        label = _clean(tds[0].get_text()).rstrip(":").strip()
        if label:
            rows[label] = _clean(tds[1].get_text(" "))
    return rows


def parse_settings(html: str) -> dict:
    """Normalize to the same shape as api.parse_settings."""
    rows = parse_settings_table(html)
    budget = re.search(r"\d+", rows.get("Salary Cap Draft Budget", ""))
    cats = re.findall(r"\(([^)]+)\)", rows.get("Players Stat Categories", ""))
    draft_time = rows.get("Draft Time", "").replace("[ Add to My Calendar ]", "").strip() or None
    return {
        "name": rows["League Name"],
        "num_teams": int(rows["Max Teams"]),
        "scoring_type": rows["Scoring Type"],
        "draft_type": rows.get("Draft Type", ""),
        "draft_budget": int(budget.group()) if budget else None,
        "draft_time": draft_time,
        "roster_positions": [p.strip() for p in rows["Roster Positions"].split(",")],
        "stat_categories": cats,
        "raw": rows,
    }


def parse_teams(html: str, league_id: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(rf"/nba/{league_id}/(\d+)/?$")
    teams: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        m = pattern.search(a["href"])
        name = _clean(a.get_text())
        if m and name and int(m.group(1)) not in teams:
            teams[int(m.group(1))] = name
    return [{"team_id": k, "name": v} for k, v in sorted(teams.items())]


def parse_previous_league(html: str) -> tuple[int, str] | None:
    """(year, league_id) of last season, from the "Last year's champion" links on the league page.

    Public pages give only one step back: the 2025 page has no link to 2024 (verified 2026-10-04).
    """
    m = re.search(r"/(20\d\d)/nba/(\d+)/\d+", html)
    return (int(m.group(1)), m.group(2)) if m else None


def parse_draft_results(html: str) -> list[dict]:
    """Rows of the draftresults "picks" tab: pick_no, yahoo_player_id, price, team_name.

    The "(DEN - C)" text after the name is the player's team and positions at fetch time,
    not on draft day, so it is not returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = next(
        (t for t in soup.find_all("table") if t.find("td", class_="cost") and t.find("td", class_="team-name")),
        None,
    )
    if table is None:
        raise ValueError("draft results table not found")
    picks = []
    for tr in table.tbody.find_all("tr"):
        player = tr.find("td", class_="player").a
        picks.append({
            "pick_no": int(_clean(tr.find("td", class_="first").get_text()).rstrip(".")),
            "yahoo_player_id": re.search(r"/players/(\d+)", player["href"]).group(1),
            "player_name": _clean(player.get_text()),
            "price": int(_clean(tr.find("td", class_="cost").get_text()).lstrip("$")),
            "team_name": _clean(tr.find("td", class_="team-name")["title"]),
        })
    return picks
