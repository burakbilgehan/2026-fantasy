"""ESPN depth charts (RotoWire data), all 30 teams, with injury status.

API (no key, verified 2026-10-17): team list at
https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams and one chart per team at
.../teams/{espn_team_id}/depthcharts. `depthchart[0].positions` has pg, sg, sf, pf, c; each an ordered
`athletes` list (first = starter) with the ESPN athlete id and `injuries[].status` ("Out", "Day-To-Day").
A player can be listed in several slots. No minutes. Chosen over Hashtag for the Depth tab and the
drawer (2026-10-17): Hashtag still listed injured or traded starters (Butler, Mark Williams, Lopez).
"""

import json
from dataclasses import dataclass

from app.sources.players.base import save_raw
from app.sources.roles import get
from app.sources.teams import canonical

KEY = "espn_depth"
TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
DEPTH_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/depthcharts"
SLOTS = ("PG", "SG", "SF", "PF", "C")


@dataclass
class DepthRow:
    team: str
    slot: str
    depth: int  # position in the slot list; 1 = starter
    order: int
    name: str
    espn_id: str
    injury: str | None  # ESPN status, e.g. "Out"


def fetch() -> dict[str, str]:
    """ESPN team id -> depth chart JSON text, for every team."""
    teams = json.loads(get(TEAMS_URL))["sports"][0]["leagues"][0]["teams"]
    out = {t["team"]["id"]: get(DEPTH_URL.format(id=t["team"]["id"])) for t in teams}
    save_raw(KEY, json.dumps(out), suffix="json")
    return out


def parse(pages: dict[str, str]) -> list[DepthRow]:
    out, teams = [], set()
    for text in pages.values():
        data = json.loads(text)
        team = canonical(data["team"]["abbreviation"])
        if team is None:
            raise ValueError(f"ESPN depth: unknown team {data['team']['abbreviation']}")
        teams.add(team)
        for key, pos in data["depthchart"][0]["positions"].items():
            slot = key.upper()
            if slot not in SLOTS:
                raise ValueError(f"ESPN depth: unknown slot {key} ({team})")
            for i, a in enumerate(pos["athletes"], start=1):
                inj = next((x.get("status") for x in a.get("injuries") or [] if x.get("status")), None)
                out.append(DepthRow(team=team, slot=slot, depth=i, order=i, name=a["displayName"],
                                    espn_id=str(a["id"]), injury=inj))
    if len(teams) != 30:
        raise ValueError(f"ESPN depth: {len(teams)} teams, expected 30")
    return out
