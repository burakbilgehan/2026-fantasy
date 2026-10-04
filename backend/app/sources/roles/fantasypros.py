"""FantasyPros season projections (https://www.fantasypros.com/nba/projections/overall.php).

Server-rendered table, about 266 players, 2026-27 (verified 2026-10-04).
Columns: PTS REB AST BLK STL FG% FT% 3PM GP MIN TO, all season totals.
MIN is total minutes, so minutes per game = MIN / GP. No shot attempts, so the
line cannot go into player_projections. The player cell has the FantasyPros id
(`fp-id-3485`) and `(OKC - PG)`: team and positions. robots.txt: Crawl-delay 5,
this page is not disallowed.
"""

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from app.sources.players.base import save_raw
from app.sources.roles import get
from app.sources.teams import canonical

KEY = "fantasypros"
URL = "https://www.fantasypros.com/nba/projections/overall.php"
COLUMNS = ("PTS", "REB", "AST", "BLK", "STL", "FG%", "FT%", "3PM", "GP", "MIN", "TO")
MIN_PLAYERS = 200


@dataclass
class FpPlayer:
    fp_id: str
    first_name: str
    last_name: str
    team: str | None
    positions: list[str]
    gp: float
    mpg: float
    extra: dict[str, Any]  # season totals and percentages, keys from COLUMNS


def fetch() -> str:
    html = get(URL)
    save_raw(KEY, html, suffix="html")
    return html


def _num(text: str) -> float:
    return float(text.replace(",", "").strip() or 0)


def parse(html: str) -> list[FpPlayer]:
    table = BeautifulSoup(html, "html.parser").find("table", id="data")
    if table is None:
        raise ValueError("FantasyPros: no projections table")
    headers = [th.get_text(strip=True) for th in table.thead.find_all("th")][1:]
    if tuple(headers) != COLUMNS:
        raise ValueError(f"FantasyPros: columns changed: {headers}")
    out = []
    for tr in table.tbody.find_all("tr"):
        cells = tr.find_all("td")
        link = cells[0].find("a", class_="player-name")
        fp_id = next(c[len("fp-id-"):] for c in link["class"] if c.startswith("fp-id-"))
        # "(OKC - PG,SG)"; a free agent may have no team part (not seen on 2026-10-04)
        tag = cells[0].find("small").get_text(strip=True).strip("()")
        team, _, pos = tag.rpartition(" - ") if " - " in tag else ("", "", tag)
        values = {c: _num(td.get_text()) for c, td in zip(COLUMNS, cells[1:])}
        if not values["GP"]:
            continue
        first, _, last = link.get_text(strip=True).partition(" ")
        out.append(FpPlayer(
            fp_id=fp_id, first_name=first, last_name=last, team=canonical(team),
            positions=[p for p in pos.split(",") if p], gp=values["GP"],
            mpg=values["MIN"] / values["GP"], extra=values,
        ))
    if len(out) < MIN_PLAYERS:
        raise ValueError(f"FantasyPros: only {len(out)} players")
    return out
