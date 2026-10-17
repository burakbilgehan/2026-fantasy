"""Depth tab (user, 2026-10-17): every team's depth chart with projected minutes from all sources.

Depth chart: ESPN (RotoWire data, `espn_depth`), Hashtag when ESPN rows are missing. Minutes: our own
projection (LLM judged, T-025), ESPN, DARKO, FantasyPros, and last season's real minutes per game.
Starting lineup research: the newest `docs/research/starting-lineups-*.json` (web research with sources).
"""

import json
import unicodedata
from collections import defaultdict

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import REPO_ROOT
from app.db import SessionLocal
from app.models import DepthChartEntry, PlayerGameLog, PlayerMinutesProjection, PlayerProjection
from app.seasons import CURRENT_SEASON, previous

router = APIRouter(prefix="/api")

SLOTS = ("PG", "SG", "SF", "PF", "C")
RESEARCH_DIR = REPO_ROOT / "docs" / "research"


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ").strip()


def depth_source(db) -> str:
    """ESPN when it has rows for the season, else Hashtag."""
    has = db.scalar(select(func.count()).select_from(DepthChartEntry).where(
        DepthChartEntry.source == "espn_depth", DepthChartEntry.season == CURRENT_SEASON))
    return "espn_depth" if has else "hashtag"


def _research() -> tuple[str | None, dict[str, dict]]:
    """(file date, team -> {"starters": {normalized name: status}, "disputed": [...], "rotation": str})."""
    files = sorted(RESEARCH_DIR.glob("starting-lineups-*.json"))
    if not files:
        return None, {}
    data = json.loads(files[-1].read_text())
    out = {}
    for t in data["teams"]:
        out[t["team"]] = {
            "starters": {_norm(s["name"]): {"status": s["status"], "role_up": s.get("role_up", False),
                                            "evidence": s["evidence"], "source_url": s.get("source_url"),
                                            "source_date": s.get("source_date")} for s in t["starters"]},
            "disputed": [{"spot": d["spot"], "candidates": d["candidates"], "lean": d["lean"],
                          "source_url": d.get("source_url"), "source_date": d.get("source_date")}
                         for d in t["disputed_spots"]],
            "rotation": t.get("rotation_notes"),
        }
    return files[-1].stem.removeprefix("starting-lineups-"), out


def _mpg(rows) -> dict[int, float]:
    return {r.player_pk: r.min / r.gp for r in rows if r.min and r.gp}


@router.get("/depth")
def depth() -> dict:
    """All 30 teams: players in depth chart order (starters first), slots, injury, minutes per source."""
    last = previous(CURRENT_SEASON)
    with SessionLocal() as db:
        source = depth_source(db)
        rows = db.scalars(select(DepthChartEntry).where(
            DepthChartEntry.source == source, DepthChartEntry.season == CURRENT_SEASON)
            .order_by(DepthChartEntry.team, DepthChartEntry.slot, DepthChartEntry.order)).all()
        fetched = max((r.fetched_at for r in rows), default=None)
        proj = {src: _mpg(db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == src, PlayerProjection.season == CURRENT_SEASON)))
            for src in ("own", "espn")}
        own_gp = {r.player_pk: r.gp for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "own", PlayerProjection.season == CURRENT_SEASON))}
        other: dict[str, dict[int, float]] = defaultdict(dict)
        for r in db.scalars(select(PlayerMinutesProjection).where(PlayerMinutesProjection.season == CURRENT_SEASON)):
            other[r.source][r.player_pk] = r.mpg
        past = {pk: (gp, m / gp if gp else None) for pk, gp, m in db.execute(
            select(PlayerGameLog.player_pk, func.count(), func.sum(PlayerGameLog.min))
            .where(PlayerGameLog.season == last, PlayerGameLog.season_type == "regular")
            .group_by(PlayerGameLog.player_pk))}
    research_date, research = _research()

    teams: dict[str, dict] = {}
    for r in rows:
        team = teams.setdefault(r.team, {"team": r.team, "players": {}})
        key = r.player_pk or r.player_name
        p = team["players"].get(key)
        if p is None:
            pk = r.player_pk
            gp, mpg = past.get(pk, (None, None)) if pk else (None, None)
            res = research.get(r.team, {}).get("starters", {}).get(_norm(r.player_name))
            p = team["players"][key] = {
                "player_id": pk, "name": r.player_name, "slots": [], "starter_slot": None, "injury": r.injury,
                "minutes": {"own": proj["own"].get(pk), "espn": proj["espn"].get(pk),
                            "darko": other["darko"].get(pk), "fantasypros": other["fantasypros"].get(pk)},
                "own_gp": own_gp.get(pk), "last": {"season": last, "gp": gp, "mpg": mpg}, "research": res,
            }
        p["slots"].append(f"{r.slot}{r.order}")
        if r.depth == 1 and p["starter_slot"] is None:
            p["starter_slot"] = r.slot
    out = []
    for code in sorted(teams):
        t = teams[code]
        ps = list(t["players"].values())
        # Starters in slot order, then the bench by our projected minutes.
        ps.sort(key=lambda p: (p["starter_slot"] is None, SLOTS.index(p["starter_slot"]) if p["starter_slot"] else 0,
                               -(p["minutes"]["own"] or 0)))
        res = research.get(code, {})
        out.append({"team": code, "players": ps, "disputed": res.get("disputed", []), "rotation": res.get("rotation")})
    return {"source": source, "fetched_at": fetched, "season": CURRENT_SEASON, "research_date": research_date, "teams": out}
