"""NBA regular season schedule from ESPN's public site API.

cdn.nba.com schedule JSON is blocked from this machine (403, verified
2026-10-04). ESPN works without a key (verified 2026-10-04): one request for the
team list, then one per team. Each team shows 80 games before the NBA Cup group
stage ends; the last 2 games per team are added in December, so re-sync then.
Raw copies in data/raw/espn_schedule/.
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.seasons import end_year
from app.sources.players.base import save_raw
from app.sources.teams import canonical

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Game:
    source_game_id: str
    start_utc: datetime
    game_date_et: date  # Yahoo fantasy days and weeks follow US Eastern time
    home: str
    away: str
    neutral_site: bool


def fetch(season: str, http: httpx.Client | None = None) -> dict:
    """{"teams": <teams response>, "schedules": {espn_team_id: <schedule response>}}"""
    http = http or httpx.Client(timeout=30)
    teams = http.get(f"{BASE}/teams").raise_for_status().json()
    schedules = {}
    for tid in team_ids(teams):
        resp = http.get(
            f"{BASE}/teams/{tid}/schedule", params={"season": end_year(season), "seasontype": 2}
        )
        schedules[tid] = resp.raise_for_status().json()
    payload = {"teams": teams, "schedules": schedules}
    save_raw("espn_schedule", payload)
    return payload


def team_ids(teams: dict) -> list[str]:
    return [t["team"]["id"] for t in teams["sports"][0]["leagues"][0]["teams"]]


def parse(raw: dict, season: str) -> list[Game]:
    """All regular season games, each once. Raises if a team is not one of the 30."""
    games: dict[str, Game] = {}
    for sched in raw["schedules"].values():
        for ev in sched.get("events", []):
            if ev["season"]["year"] != end_year(season) or ev["seasonType"]["type"] != 2:
                continue
            comp = ev["competitions"][0]
            side = {}
            for c in comp["competitors"]:
                abbr = canonical(c["team"]["abbreviation"])
                if abbr is None:
                    raise ValueError(f"ESPN event {ev['id']}: unknown team {c['team']['abbreviation']}")
                side[c["homeAway"]] = abbr
            start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            games[ev["id"]] = Game(
                source_game_id=ev["id"],
                start_utc=start,
                game_date_et=start.astimezone(ET).date(),
                home=side["home"],
                away=side["away"],
                neutral_site=bool(comp.get("neutralSite")),
            )
    return sorted(games.values(), key=lambda g: (g.start_utc, g.source_game_id))
