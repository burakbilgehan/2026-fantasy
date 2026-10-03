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

BASE_URL = "https://basketball.fantasysports.yahoo.com/nba"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 2026-fantasy personal read-only"


def fetch(league_id: str, page: str = "", http: httpx.Client | None = None) -> str:
    http = http or httpx.Client(timeout=20, follow_redirects=True)
    resp = http.get(f"{BASE_URL}/{league_id}/{page}", headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    html = resp.content.decode("utf-8")
    cache_dir = RAW_DIR / "yahoo_web"
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = page.strip("/").replace("/", "_") or "league"
    (cache_dir / f"{league_id}_{name}_{int(time.time())}.html").write_text(html, encoding="utf-8")
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
