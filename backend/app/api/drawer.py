"""Player drawer data (T-028): player card, team depth chart with minutes, articles.

Rank and dollars in every model: `GET /api/valuation/player/{id}`. Tags: `GET /api/knowledge/players/{id}/tags`.
"""

import re

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.valuation import nba_ids
from app.db import SessionLocal
from app.knowledge import index, stats
from app.models import DepthChartEntry, PlayerAdvancedStats, Player, PlayerMarketValue, PlayerMinutesProjection, PlayerProjection
from app.seasons import CURRENT_SEASON

router = APIRouter(prefix="/api")

SLOTS = ("PG", "SG", "SF", "PF", "C")


@router.get("/players/{player_pk}/card")
def player_card(player_pk: int) -> dict:
    """Header facts, the profile page (or a code-made stat table when there is no profile) and articles."""
    with SessionLocal() as db:
        p = db.get(Player, player_pk)
        if not p:
            raise HTTPException(404, f"no player {player_pk}")
        yahoo = db.scalar(select(PlayerMarketValue).where(
            PlayerMarketValue.player_pk == player_pk, PlayerMarketValue.source == "yahoo",
            PlayerMarketValue.season == CURRENT_SEASON))
        espn = db.scalar(select(PlayerMarketValue).where(
            PlayerMarketValue.player_pk == player_pk, PlayerMarketValue.source == "espn",
            PlayerMarketValue.season == CURRENT_SEASON))
        fantrax = db.scalar(select(PlayerMarketValue).where(
            PlayerMarketValue.player_pk == player_pk, PlayerMarketValue.source == "fantrax",
            PlayerMarketValue.season == CURRENT_SEASON))
        numbers = stats.load(db, player_pk)
        usage = [{"season": a.season, "usg_pct": a.usg_pct, "ts_pct": a.ts_pct, "gp": a.gp}
                 for a in db.scalars(select(PlayerAdvancedStats).where(
                     PlayerAdvancedStats.player_pk == player_pk, PlayerAdvancedStats.source == "nba")
                     .order_by(PlayerAdvancedStats.season.desc()))]
    slugs = index.player_slugs()
    slug = next((s for s, pk in slugs.items() if pk == player_pk), None)
    page = index.read_page(index.PLAYER_MD_DIR / f"{slug}.md") if slug else None
    if page:
        report = index.for_drawer(page, slugs)
    else:
        report = f"{stats.stat_table(numbers, newest_first=True)}\n\n{stats.price_table(numbers)}\n"
    return {
        "player_id": player_pk,
        "nba_id": nba_ids([player_pk]).get(player_pk),
        "name": f"{p.first_name} {p.last_name}".strip(),
        "team": p.team,
        # Same rule as the value table: current Yahoo positions, else the identity source's position.
        "positions": (yahoo.positions if yahoo else None) or ([p.position] if p.position else None),
        "injury": yahoo.injury if yahoo else None,
        "injury_note": yahoo.injury_note if yahoo else None,
        "prices": {
            "yahoo_average_cost": yahoo.average_cost if yahoo else None,
            "espn_average_cost": espn.average_cost if espn else None,
            "fantrax_adp": fantrax.average_pick if fantrax else None,
            "league_last": numbers.league_price,
            "league_last_season": numbers.league_season,
        },
        "usage": usage,  # newest season first
        "has_profile": page is not None,
        "report": report,
        "articles": index.article_index(slugs).get(player_pk, []),
    }


@router.get("/knowledge/articles/{slug}")
def article(slug: str) -> dict:
    path = index.article_path(slug)
    if not path:
        raise HTTPException(404, f"no article {slug}")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^# (.+)$", text, re.M)
    return {"slug": slug, "title": m.group(1).strip() if m else slug,
            "markdown": index.for_drawer(text, index.player_slugs())}


@router.get("/teams/{team}/depth")
def team_depth(team: str) -> dict:
    """Depth chart (Hashtag) per slot with projected minutes per game from ESPN, DARKO and FantasyPros,
    and the team profile page. Unmatched depth chart names keep `player_id: null`."""
    if not re.fullmatch(r"[A-Z]{2,4}", team):
        raise HTTPException(400, "team must be a team code like DEN")
    with SessionLocal() as db:
        rows = db.scalars(select(DepthChartEntry).where(
            DepthChartEntry.team == team, DepthChartEntry.season == CURRENT_SEASON)
            .order_by(DepthChartEntry.slot, DepthChartEntry.order)).all()
        pks = {r.player_pk for r in rows if r.player_pk}
        espn = {r.player_pk: r.min / r.gp for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "espn", PlayerProjection.season == CURRENT_SEASON,
            PlayerProjection.player_pk.in_(pks))) if r.min and r.gp}
        fantrax = {r.player_pk: r.min / r.gp for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "fantrax", PlayerProjection.season == CURRENT_SEASON,
            PlayerProjection.player_pk.in_(pks))) if r.min and r.gp}
        fanscout = {r.player_pk: r.min / r.gp for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "fanscout", PlayerProjection.season == CURRENT_SEASON,
            PlayerProjection.player_pk.in_(pks))) if r.min and r.gp}
        other: dict[str, dict[int, float]] = {}
        for r in db.scalars(select(PlayerMinutesProjection).where(
                PlayerMinutesProjection.season == CURRENT_SEASON, PlayerMinutesProjection.player_pk.in_(pks))):
            other.setdefault(r.source, {})[r.player_pk] = r.mpg
        fetched = max((r.fetched_at for r in rows), default=None)
    slots = {s: [] for s in SLOTS}
    for r in rows:
        pk = r.player_pk
        slots.setdefault(r.slot, []).append({
            "player_id": pk, "name": r.player_name, "depth": r.depth,
            "minutes": {"espn": espn.get(pk), "fanscout": fanscout.get(pk), "fantrax": fantrax.get(pk), "darko": other.get("darko", {}).get(pk),
                        "fantasypros": other.get("fantasypros", {}).get(pk)},
        })
    page = index.read_page(index.TEAM_MD_DIR / f"{team}.md")
    return {
        "team": team,
        "source": "hashtag",
        "fetched_at": fetched,
        "slots": [{"slot": s, "players": ps} for s, ps in slots.items() if ps],
        "report": index.for_drawer(page, index.player_slugs()) if page else None,
    }


# T-025: the order and names of the projection lines in the drawer.
PROJECTION_LINES = (
    ("own", "Own (LLM judged)"), ("own-floor", "Own floor"), ("own-ceiling", "Own ceiling"),
    ("own-base", "Own base (consensus)"), ("yahoo", "Yahoo"), ("fanscout", "FanScout"), ("fantrax", "Fantrax"),
    ("espn", "ESPN"), ("own-stat", "Own stat model"),
)


@router.get("/players/{player_pk}/projection")
def player_projection(player_pk: int) -> dict:
    """Own projection (T-025) for the drawer: every source's line next to ours, last season's real
    line, usage history and projection, and the LLM's (and manual) adjustments with reasons."""
    from sqlalchemy import func

    from app.models import PlayerGameLog, PlayerSeasonStats, ProjectionAdjustment
    from app.seasons import previous

    fields = ("gp", "min", "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
    with SessionLocal() as db:
        if not db.get(Player, player_pk):
            raise HTTPException(404, f"no player {player_pk}")
        rows = {r.source: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.player_pk == player_pk, PlayerProjection.season == CURRENT_SEASON))}
        lines = [{"key": k, "label": label, **{f: getattr(rows[k], f) for f in fields}}
                 for k, label in PROJECTION_LINES if k in rows and rows[k].gp]
        last = previous(CURRENT_SEASON)
        actual = db.scalar(select(PlayerSeasonStats).where(
            PlayerSeasonStats.player_pk == player_pk, PlayerSeasonStats.source == "nba",
            PlayerSeasonStats.season == last))
        if actual and actual.gp:
            minutes = db.scalar(select(func.sum(PlayerGameLog.min)).where(
                PlayerGameLog.player_pk == player_pk, PlayerGameLog.season == last,
                PlayerGameLog.season_type == "regular"))
            lines.append({"key": "actual", "label": f"{last} actual",
                          **{f: getattr(actual, f) for f in fields}, "min": minutes})
        adj = sorted(db.scalars(select(ProjectionAdjustment).where(
            ProjectionAdjustment.player_pk == player_pk, ProjectionAdjustment.season == CURRENT_SEASON)),
            key=lambda a: a.source != "manual")
        history = [{"season": a.season, "usg_pct": a.usg_pct} for a in db.scalars(select(PlayerAdvancedStats).where(
            PlayerAdvancedStats.player_pk == player_pk, PlayerAdvancedStats.source == "nba")
            .order_by(PlayerAdvancedStats.season.desc())) if a.usg_pct is not None]
    own = rows.get("own")
    return {
        "season": CURRENT_SEASON,
        "lines": lines,
        "usage": {"projected": next((a.usg for a in adj if a.usg is not None), None), "history": history},
        "judgment": [{
            "source": a.source, "model": a.model, "updated_at": a.updated_at.isoformat(timespec="minutes"),
            "usg": a.usg, "mpg": a.mpg, "gp": a.gp, "games_out": a.games_out, "late_games_out": a.late_games_out,
            "multipliers": a.multipliers or {}, "summary": a.note, "reasons": a.reasons or [],
        } for a in adj],
        "base_sources": (own.extra or {}).get("sources", []) if own else [],
    }
