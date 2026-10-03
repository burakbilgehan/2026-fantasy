"""Sync league settings and teams into the DB.

Tries the Yahoo API first. Falls back to the public league pages when the API
is not approved (YahooAccessDenied) or there is no token.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import League, Team
from app.sources.yahoo import api, web
from app.sources.yahoo.factory import make_api_client

log = logging.getLogger(__name__)


def fetch_league(league_id: str) -> tuple[dict, list[dict], str]:
    league_key = f"nba.l.{league_id}"
    try:
        client = make_api_client()
        settings = api.parse_settings(client.league_settings(league_key))
        teams = api.parse_teams(client.league_teams(league_key))
        return settings, teams, "yahoo_api"
    except (api.YahooAccessDenied, RuntimeError) as exc:
        log.warning("Yahoo API unavailable (%s). Using public league pages.", exc)
    settings = web.parse_settings(web.fetch(league_id, "settings"))
    teams = web.parse_teams(web.fetch(league_id), league_id)
    return settings, teams, "yahoo_web"


def sync_league(league_id: str | None = None) -> League:
    league_id = league_id or get_settings().yahoo_league_id
    settings, teams, source = fetch_league(league_id)
    init_db()
    with SessionLocal.begin() as db:
        league = db.scalar(select(League).where(League.league_id == league_id))
        if league is None:
            league = League(league_id=league_id)
            db.add(league)
        league.name = settings["name"]
        league.num_teams = settings["num_teams"]
        league.scoring_type = settings["scoring_type"]
        league.draft_type = settings["draft_type"]
        league.draft_budget = settings["draft_budget"]
        league.draft_time = settings["draft_time"]
        league.roster_positions = settings["roster_positions"]
        league.stat_categories = settings["stat_categories"]
        league.raw_settings = settings["raw"]
        league.source = source
        league.synced_at = datetime.now(UTC)
        db.flush()
        db.execute(delete(Team).where(Team.league_pk == league.id))
        db.add_all(Team(league_pk=league.id, team_id=t["team_id"], name=t["name"]) for t in teams)
    return league


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    lg = sync_league()
    print(f"Synced {lg.name} ({lg.league_id}) from {lg.source}")
