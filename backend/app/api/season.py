"""Season H2H simulation of the drafted rosters (user, 2026-10-18). Work: `app/analytics/season_sim.py`.

Rosters: the live draft board of the league. Player lines: the value table base (`kind`, `source`, `season`).
Calendar and matchups: `data/raw/yahoo/{league}_schedule.json`, captured with
`app/sources/yahoo/schedule_capture.js` (the Yahoo Fantasy API is not approved for our app).
NBA game days: the `nba_schedule` table (ESPN).
"""

import json
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.analytics import season_sim as ss
from app.api.valuation import DEFAULTS, values
from app.config import RAW_DIR
from app.db import SessionLocal
from app.draft import live
from app.models import NbaGame
from app.seasons import CURRENT_SEASON

router = APIRouter(prefix="/api/season")


def _calendar(league_id: str) -> tuple[list[ss.Week], dict[int, list[tuple[int, int]]]]:
    path = RAW_DIR / "yahoo" / f"{league_id}_schedule.json"
    if not path.exists():
        raise HTTPException(404, f"No Yahoo calendar for league {league_id}: run schedule_capture.js")
    data = json.loads(path.read_text())
    weeks = [ss.Week(w["week"], date.fromisoformat(w["first"]), date.fromisoformat(w["last"])) for w in data["weeks"]]
    return weeks, {w["week"]: [tuple(m) for m in w["matchups"]] for w in data["weeks"]}


def _plays(season: str) -> dict[date, set[str]]:
    with SessionLocal() as db:
        rows = db.execute(select(NbaGame.home, NbaGame.away, NbaGame.game_date_et).where(NbaGame.season == season)).all()
    out: dict[date, set[str]] = defaultdict(set)
    for home, away, d in rows:
        out[d] |= {home, away}
    return out


@router.get("/sim/{league_id}")
def sim(league_id: str, kind: str = DEFAULTS["kind"], source: str = DEFAULTS["source"],
        season: str = CURRENT_SEASON) -> dict:
    d = live.get(league_id)
    if d is None:
        raise HTTPException(404, f"No draft capture for league {league_id}")
    with live.lock:
        picks = list(d.state.picks.values())
        names = dict(d.team_names)
        my = d.my_team_id
    from app.api.draft import _yahoo_pks

    pks = _yahoo_pks()
    rows = {r["player_id"]: r for r in values(kind=kind, source=source, season=season)["players"]}
    rosters: dict[int, list[ss.SimPlayer]] = defaultdict(list)
    missing = []
    for p in picks:
        pk = pks.get(p.player_id)
        sp = ss.sim_player(pk, rows[pk]) if pk in rows else None
        if sp is None:
            missing.append(p.player_id)
        else:
            rosters[p.team_id].append(sp)

    weeks, matchups = _calendar(league_id)
    plays = _plays(season)
    if not plays:
        raise HTTPException(404, f"No NBA schedule for {season}")
    res = ss.season(dict(rosters), weeks, plays, matchups)
    lines = res["lines"]

    teams = []
    for t in sorted(rosters):
        ls = lines[t]
        teams.append({
            "team_id": t, "name": names.get(t), "mine": t == my,
            "record": res["record"].get(t, [0, 0, 0]), "allplay": res["allplay"].get(t, [0, 0, 0]),
            "used": round(sum(w["used"] for w in ls), 1), "available": round(sum(w["available"] for w in ls), 1),
            "slot_days": sum(w["slot_days"] for w in ls),
            "playoff_used": round(sum(w["used"] for w in ls if w["week"] >= 19), 1),
        })
    week_out = []
    for wi, w in enumerate(weeks):
        week_out.append({
            "week": w.week, "first": w.first.isoformat(), "last": w.last.isoformat(),
            "teams": {t: {"cats": {c: round(v, 4) for c, v in lines[t][wi]["cats"].items()},
                          "used": round(lines[t][wi]["used"], 2), "available": round(lines[t][wi]["available"], 2)}
                      for t in rosters},
            "matchups": [r for r in res["results"] if r["week"] == w.week],
        })
    return {"league_id": league_id, "my_team_id": my, "base": {"kind": kind, "source": source, "season": season},
            "teams": teams, "weeks": week_out, "missing": missing, "cats": list(ss.CATS)}
