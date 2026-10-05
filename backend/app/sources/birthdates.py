"""Player birth dates: ESPN team rosters, ESPN athlete pages, and an age fallback.

1. Rosters: site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/roster.
   Team ids come from .../nba/teams (30 teams, ids 1 to 30 on 2026-10-05). Every
   athlete has `id` (the same id as the ESPN fantasy feed: 373 of 373 id matches had
   the same name, verified 2026-10-05), `firstName`, `lastName` and `dateOfBirth`
   like "1998-09-02T07:00Z" (606 athletes, all with a date, verified 2026-10-05).
   The date part is the birth date; the time is a time zone artifact.
2. Athletes: sports.core.api.espn.com/v2/sports/basketball/leagues/nba/athletes/{id}.
   Same `dateOfBirth` field, also for free agents and retired players (verified
   2026-10-05, Russell Westbrook). One call per player: used only for players that
   are not on a roster and have an ESPN id. (site.web.api.espn.com/.../athletes/{id}
   returns dateOfBirth null; do not use it.)
3. Age fallback ("nba_age"): stats.nba.com `leaguedashplayerstats` AGE, stored in
   player_advanced_stats.extra["age"]. AGE is the age on about June 30 of the
   season's end year (fit against ESPN dates, 2026-10-05: 407 of 407 players right
   for 2024-25, 476 of 478 for 2025-26). A birth date from it is the middle of the
   possible range, so it can be off by up to 6 months. Approximate only.

Public, undocumented endpoints, no login. Raw copies in data/raw/espn_bio/.
Sources never touch the DB. Job: app/jobs/sync_birthdates.py.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from app.seasons import end_year
from app.sources.players.base import save_raw

KEY = "espn_bio"
TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
ROSTER_URL = TEAMS_URL + "/{team_id}/roster"
ATHLETE_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/athletes/{id}"
MIN_TEAMS = 30
MIN_ATHLETES = 400  # 606 on 2026-10-05 (preseason rosters)


@dataclass
class EspnBirth:
    espn_id: str
    first_name: str
    last_name: str
    birth_date: date | None


def _client(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=30, follow_redirects=True)


def fetch_rosters(http: httpx.Client | None = None) -> dict:
    """{"teams": <teams JSON>, "rosters": {team id: <roster JSON>}}"""
    http = _client(http)
    teams = http.get(TEAMS_URL).raise_for_status().json()
    ids = [t["team"]["id"] for t in teams["sports"][0]["leagues"][0]["teams"]]
    rosters = {i: http.get(ROSTER_URL.format(team_id=i)).raise_for_status().json() for i in ids}
    payload = {"teams": teams, "rosters": rosters}
    save_raw(KEY, payload)
    return payload


def fetch_athletes(espn_ids: list[str], http: httpx.Client | None = None) -> dict[str, dict]:
    """{espn id: <athlete JSON>}. A 404 (unknown id) is skipped."""
    http = _client(http)
    out = {}
    for i in espn_ids:
        resp = http.get(ATHLETE_URL.format(id=i))
        if resp.status_code == 404:
            continue
        out[i] = resp.raise_for_status().json()
    if out:
        save_raw(KEY, {"athletes": out})
    return out


def _birth(a: dict) -> EspnBirth:
    dob = a.get("dateOfBirth")
    return EspnBirth(espn_id=str(a["id"]), first_name=a.get("firstName") or "",
                     last_name=a.get("lastName") or "",
                     birth_date=date.fromisoformat(dob[:10]) if dob else None)


def parse_rosters(raw: dict) -> list[EspnBirth]:
    """Pure. One row per athlete on a roster; a player listed twice counts once."""
    if len(raw["rosters"]) < MIN_TEAMS:
        raise ValueError(f"ESPN rosters: only {len(raw['rosters'])} teams")
    out: dict[str, EspnBirth] = {}
    for roster in raw["rosters"].values():
        for a in roster["athletes"]:
            out.setdefault(str(a["id"]), _birth(a))
    if len(out) < MIN_ATHLETES:
        raise ValueError(f"ESPN rosters: only {len(out)} athletes")
    return list(out.values())


def parse_athletes(raw: dict[str, dict]) -> list[EspnBirth]:
    """Pure. raw = {espn id: athlete JSON}."""
    return [_birth(a) for a in raw.values()]


def approx_birth_date(season: str, age: float) -> date:
    """Middle of the birth date range for AGE on June 30 of the season's end year.

    Age A on day R means birth in (R - (A+1) years, R - A years]. The middle is
    R - A years - 6 months, about Dec 30 of (end year - A - 1).
    """
    ref = date(end_year(season) - int(age), 6, 30)
    return ref - timedelta(days=182)
