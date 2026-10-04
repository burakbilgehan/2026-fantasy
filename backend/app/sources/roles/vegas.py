"""NBA season win totals (over/under lines) from sportsbettingdime.com.

https://www.sportsbettingdime.com/nba/futures/win-totals-best-odds/ : one table,
Team / Win Total / Over Odds / Under Odds, all 30 teams (verified 2026-10-04).
The page keeps a dated "odds movement timeline"; some lines may still be the
August openers. The season is not in the table; it is read from the heading
"2026-27 NBA Season Win Totals" and checked against the season asked for.
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.sources.players.base import save_raw
from app.sources.roles import get
from app.sources.teams import from_full_name

KEY = "sportsbettingdime"
URL = "https://www.sportsbettingdime.com/nba/futures/win-totals-best-odds/"


@dataclass
class WinTotal:
    team: str
    wins: float
    over_odds: int | None
    under_odds: int | None


def fetch() -> str:
    html = get(URL)
    save_raw(KEY, html, suffix="html")
    return html


def _odds(text: str) -> int | None:
    text = text.strip().replace("−", "-")
    return int(text) if re.fullmatch(r"[+-]?\d+", text) else None


def parse(html: str, season: str) -> list[WinTotal]:
    soup = BeautifulSoup(html, "html.parser")
    heading = next((h for h in soup.find_all(["h2", "h3"])
                    if re.search(r"\d{4}-\d{2} NBA Season Win Totals", h.get_text())), None)
    if heading is None or season not in heading.get_text():
        raise ValueError(f"Vegas: no win totals heading for {season}")
    table = heading.find_next("table")
    out = []
    for tr in table.tbody.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        team = from_full_name(cells[0])
        if team is None:
            raise ValueError(f"Vegas: unknown team {cells[0]}")
        out.append(WinTotal(team=team, wins=float(cells[1]),
                            over_odds=_odds(cells[2]), under_odds=_odds(cells[3])))
    if len({w.team for w in out}) != 30:
        raise ValueError(f"Vegas: {len(out)} rows, expected 30 teams")
    return out
