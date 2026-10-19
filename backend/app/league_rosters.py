"""Current league rosters (user, 2026-10-19: the season started, trades and waivers change teams).

Source: the public Yahoo `startingrosters` page (no login, `sources/yahoo/web.parse_rosters`). The Yahoo
Fantasy API is still not approved for our app. Saved to data/raw/yahoo/{league}_rosters.json with the
fetch time; `refresh` runs on the user's "Update" button. Before the first refresh: the draft picks.
"""

import json
from datetime import UTC, datetime

from app.config import RAW_DIR
from app.sources.yahoo import web

DIR = RAW_DIR / "yahoo"


def _path(league_id: str):
    return DIR / f"{league_id}_rosters.json"


def refresh(league_id: str) -> dict:
    teams = web.parse_rosters(web.fetch(league_id, "startingrosters"))
    if not teams:
        raise ValueError("no rosters on the startingrosters page")
    data = {"league_id": league_id, "fetched_at": datetime.now(UTC).isoformat(), "source": "yahoo startingrosters",
            "teams": teams}
    DIR.mkdir(parents=True, exist_ok=True)
    _path(league_id).write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data


def load(league_id: str) -> dict | None:
    p = _path(league_id)
    return json.loads(p.read_text()) if p.exists() else None
