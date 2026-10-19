"""Trade page (VISION M5, user 2026-10-19). Work: `app/analytics/trade.py`.

Rosters: `app/league_rosters.py` (public Yahoo page; the "Update" button refetches it), else the draft picks.
Player lines and our values: the value table with the page's base and model. Calendar, matchups and NBA
game days: the same inputs as the season sim (`app/api/season.py`).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import league_rosters
from app.analytics import trade as tr
from app.api import season as season_api
from app.api.valuation import DEFAULTS, values
from app.draft import live
from app.seasons import CURRENT_SEASON

router = APIRouter(prefix="/api/trade")


class Base(BaseModel):
    kind: str = DEFAULTS["kind"]
    source: str = DEFAULTS["source"]
    season: str = CURRENT_SEASON
    model: str = DEFAULTS["model"]
    dollars: str = DEFAULTS["dollars"]
    pool: int = DEFAULTS["pool"]


class TradeBody(Base):
    give: list[int] = []
    get: list[int] = []
    partner: int | None = None
    improve: list[str] = []
    max_size: int = 3
    min_their_yahoo: float = -4.0


_ctx: dict[tuple, tr.Context] = {}


def _rosters(league_id: str) -> tuple[dict[int, list[int]], dict[int, str], dict[int, dict], str | None, list[str]]:
    """(team -> pks, team names, pk -> {slot, status}, fetched_at, unmatched names)."""
    from app.api.draft import _yahoo_pks

    pks = _yahoo_pks()
    data = league_rosters.load(league_id)
    rosters, names, info, missing = {}, {}, {}, []
    if data:
        for t in data["teams"]:
            names[t["team_id"]] = t["name"]
            rosters[t["team_id"]] = []
            for p in t["players"]:
                pk = pks.get(p["yahoo_player_id"])
                if pk is None:
                    missing.append(p["name"])
                    continue
                rosters[t["team_id"]].append(pk)
                info[pk] = {"slot": p["slot"], "status": p["status"]}
        return rosters, names, info, data["fetched_at"], missing
    d = live.get(league_id)
    if d is None:
        raise HTTPException(404, f"No rosters for league {league_id}: press Update")
    with live.lock:
        for p in d.state.picks.values():
            if (pk := pks.get(p.player_id)) is not None:
                rosters.setdefault(p.team_id, []).append(pk)
        names = dict(d.team_names)
    return rosters, names, info, None, missing


def _my_team(league_id: str) -> int:
    d = live.get(league_id)
    if d is None or d.my_team_id is None:
        raise HTTPException(404, "My team id is unknown (no draft capture)")
    return d.my_team_id


def context(league_id: str, b: Base) -> tuple[tr.Context, dict, str | None, list[str]]:
    rosters, names, info, fetched_at, missing = _rosters(league_id)
    key = (league_id, b.kind, b.source, b.season, b.model, b.dollars, b.pool, fetched_at)
    if key not in _ctx:
        rows = {r["player_id"]: r for r in values(kind=b.kind, source=b.source, season=b.season, model=b.model,
                                                    dollars=b.dollars, pool=b.pool)["players"]}
        rosters = {t: [p for p in v if p in rows] for t, v in rosters.items()}
        weeks, matchups = season_api._calendar(league_id)
        _ctx.clear()
        _ctx[key] = tr.Context(rows=rows, rosters=rosters, names=names, me=_my_team(league_id), weeks=weeks,
                               matchups=matchups, plays=season_api._plays(b.season))
    return _ctx[key], info, fetched_at, missing


def _player(ctx: tr.Context, pk: int, info: dict) -> dict:
    r = ctx.rows[pk]
    return {"pk": pk, "name": r["name"], "team": r.get("team"), "positions": r.get("positions"),
            "injury": r.get("injury"), "yahoo": ctx.yahoo(pk), "ours": round(ctx.ours(pk), 1),
            "slot": info.get(pk, {}).get("slot"), "status": info.get(pk, {}).get("status")}


def _state(league_id: str, b: Base) -> dict:
    ctx, info, fetched_at, missing = context(league_id, b)
    return {
        "league_id": league_id, "me": ctx.me, "fetched_at": fetched_at,
        "source": "yahoo startingrosters" if fetched_at else "draft picks", "unmatched": missing,
        "teams": [{"team_id": t, "name": ctx.names.get(t), "mine": t == ctx.me,
                   "players": sorted((_player(ctx, p, info) for p in v), key=lambda x: -x["ours"])}
                  for t, v in sorted(ctx.rosters.items())],
    }


@router.post("/{league_id}/state")
def state(league_id: str, b: Base) -> dict:
    return _state(league_id, b)


@router.post("/{league_id}/refresh")
def refresh(league_id: str, b: Base) -> dict:
    try:
        league_rosters.refresh(league_id)
    except Exception as exc:  # network or page change: say so, keep the last saved rosters
        raise HTTPException(502, f"Yahoo rosters could not be read: {exc}") from exc
    _ctx.clear()
    return _state(league_id, b)


def _check(ctx: tr.Context, body: TradeBody) -> None:
    owner = {pk: t for t, v in ctx.rosters.items() for pk in v}
    if any(owner.get(p) != ctx.me for p in body.give):
        raise HTTPException(400, "Every player I give must be on my roster")
    if body.get and len({owner.get(p) for p in body.get}) != 1:
        raise HTTPException(400, "Every player I get must come from one team")
    if body.get and owner.get(body.get[0]) == ctx.me:
        raise HTTPException(400, "I cannot get my own player")
    bad = [c for c in body.improve if c not in tr.CATS]
    if bad:
        raise HTTPException(400, f"Unknown categories: {bad}")


@router.post("/{league_id}/evaluate")
def evaluate(league_id: str, body: TradeBody) -> dict:
    ctx, _, _, _ = context(league_id, body)
    _check(ctx, body)
    owner = {pk: t for t, v in ctx.rosters.items() for pk in v}
    partner = owner[body.get[0]] if body.get else body.partner
    if partner is None or partner == ctx.me:
        raise HTTPException(400, "Pick a partner team")
    return tr.evaluate(ctx, body.give, body.get, partner)


@router.post("/{league_id}/find")
def find(league_id: str, body: TradeBody) -> dict:
    ctx, _, _, _ = context(league_id, body)
    _check(ctx, body)
    res = tr.find(ctx, body.give, body.get, body.improve, partner=body.partner, max_size=min(body.max_size, 3),
                  min_their_yahoo=body.min_their_yahoo)
    return {"results": res}
