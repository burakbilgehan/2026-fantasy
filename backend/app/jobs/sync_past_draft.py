"""Fetch last season's auction draft results from the public league pages.

Chain: current league page -> "Last year's champion" link -> /{year}/nba/{id}/.
Public pages give one season back only. Older seasons were snake drafts (no prices).
Writes drafts (kind "past_league"), draft_teams, draft_picks. Idempotent.
Usage: python -m app.jobs.sync_past_draft [league_id]  (default: our league)
"""

import sys
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Draft, DraftPick, DraftTeam
from app.seasons import label
from app.sources.yahoo import web


def fetch_pages(league_id: str) -> tuple[int, str, dict[str, str]]:
    """Returns (year, past league id, {page: html}) for settings, standings, draftresults."""
    http = httpx.Client(timeout=20, follow_redirects=True)
    prev = web.parse_previous_league(web.fetch(league_id, http=http))
    if prev is None:
        raise RuntimeError(f"No link to last season on league {league_id} page")
    year, past_id = prev
    pages = {p: web.fetch(past_id, p, http=http, year=year) for p in ("settings", "standings", "draftresults")}
    return year, past_id, pages


def store(db: Session, year: int, league_id: str, pages: dict[str, str]) -> Draft:
    settings = web.parse_settings(pages["settings"])
    if "Salary Cap" not in settings["draft_type"]:
        raise ValueError(f"{year} draft is {settings['draft_type']!r}, not an auction")
    teams = {t["name"]: t["team_id"] for t in web.parse_teams(pages["standings"], league_id)}
    picks = web.parse_draft_results(pages["draftresults"])
    unknown = {p["team_name"] for p in picks} - teams.keys()
    if unknown:
        raise ValueError(f"Draft teams not on the standings page: {sorted(unknown)}")

    draft = db.scalar(select(Draft).where(Draft.yahoo_league_id == league_id))
    if draft is None:
        draft = Draft(yahoo_league_id=league_id)
        db.add(draft)
    draft.kind = "past_league"
    draft.season = label(year)
    draft.my_team_id = None
    draft.budget = settings["draft_budget"]
    draft.source = "yahoo_web"
    draft.capture_dir = str(web.CACHE_DIR)
    draft.first_event_at = draft.last_event_at = None
    draft.ingested_at = datetime.now(UTC)
    db.flush()

    db.execute(delete(DraftTeam).where(DraftTeam.draft_pk == draft.id))
    db.execute(delete(DraftPick).where(DraftPick.draft_pk == draft.id))
    db.add_all(DraftTeam(draft_pk=draft.id, team_id=t, name=n) for n, t in sorted(teams.items(), key=lambda x: x[1]))
    db.add_all(
        DraftPick(
            draft_pk=draft.id, pick_no=p["pick_no"], team_id=teams[p["team_name"]],
            yahoo_player_id=p["yahoo_player_id"], price=p["price"],
        )
        for p in picks
    )
    return draft


if __name__ == "__main__":
    from app.db import SessionLocal, init_db

    init_db()
    year, past_id, pages = fetch_pages(sys.argv[1] if len(sys.argv) > 1 else get_settings().yahoo_league_id)
    with SessionLocal.begin() as db:
        d = store(db, year, past_id, pages)
        n = len(web.parse_draft_results(pages["draftresults"]))
        print(f"{past_id} ({d.season}, {d.kind}): {n} picks, budget {d.budget}")
