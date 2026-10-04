"""Hashtag Basketball depth charts (https://hashtagbasketball.com/nba-depth-charts).

Free, all 30 teams, "Projected 2026-27 depth charts" (verified 2026-10-04).
One `section.dc-team` per team (`id="team-ATL"`; Hashtag uses GS, NO, NY, PHO, SA).
Per slot (PG, SG, SF, PF, C): the starter in `.dc-tile`, then backups in
`ol.dc-backups`, each with a tier number in `<b>` (2 = second unit, 3, 4).
Several players can share a tier. A player can be listed in more than one slot.
No minutes.
"""

from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.sources.players.base import save_raw
from app.sources.roles import get
from app.sources.teams import canonical

KEY = "hashtag"
URL = "https://hashtagbasketball.com/nba-depth-charts"
SLOTS = ("PG", "SG", "SF", "PF", "C")


@dataclass
class DepthRow:
    team: str
    slot: str
    depth: int  # 1 = starter
    order: int  # 1-based position in the slot list
    name: str


def fetch() -> str:
    html = get(URL)
    save_raw(KEY, html, suffix="html")
    return html


def parse(html: str) -> list[DepthRow]:
    soup = BeautifulSoup(html, "html.parser")  # also decodes &#225; and &#39;
    out = []
    teams = set()
    for sec in soup.select("section.dc-team"):
        team = canonical(sec["id"].removeprefix("team-"))
        if team is None:
            raise ValueError(f"Hashtag: unknown team id {sec['id']}")
        teams.add(team)
        for col in sec.select(".dc-col"):
            slot = col.select_one(".dc-pos").get_text(strip=True)
            if slot not in SLOTS:
                raise ValueError(f"Hashtag: unknown slot {slot} ({team})")
            rows = []
            if tile := col.select_one(".dc-tile .dc-name"):
                rows.append((1, tile.get_text(strip=True)))
            for li in col.select("ol.dc-backups li"):
                rows.append((int(li.b.get_text(strip=True)), li.span.get_text(strip=True)))
            for i, (depth, name) in enumerate(rows, start=1):
                out.append(DepthRow(team=team, slot=slot, depth=depth, order=i, name=name))
    if len(teams) != 30:
        raise ValueError(f"Hashtag: {len(teams)} teams, expected 30")
    return out
