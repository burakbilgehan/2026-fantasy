"""Context layer of the own projection (T-025): one `claude -p` call per NBA team.

The LLM reads the team profile, the player profiles (expert notes) and the number tables,
and returns adjustments on top of the base layer. Stored in `projection_adjustments`
with source "llm"; `make projection ARGS=run` applies them. Prompts: prompts/projection_team/.
The full LLM answer is kept in data/projection_context/{team}.json for review.
"""

import json
import re
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select

from app.analytics.projection import context_data as cd
from app.config import DATA_DIR, REPO_ROOT
from app.experts import llm
from app.experts.extract import no_em_dash
from app.knowledge.profile import _load
from app.models import Player, PlayerGameLog, PlayerMinutesProjection, PlayerProjection, PlayerSeasonStats, ProjectionAdjustment
from app.seasons import CURRENT_SEASON, previous

PROMPT_DIR = REPO_ROOT / "prompts" / "projection_team"
PLAYER_MD = REPO_ROOT / "docs" / "knowledge" / "profiles" / "players"
PLAYER_JSON = REPO_ROOT / "docs" / "knowledge" / "_data" / "profiles" / "players"
TEAM_MD = REPO_ROOT / "docs" / "knowledge" / "profiles" / "teams"
OUT_DIR = DATA_DIR / "projection_context"
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge"
INPUTS_DIR = OUT_DIR / "inputs"
INPUTS_FILE = INPUTS_DIR / "league_players.csv"
CONFIG, SYSTEM, USER_PROMPT, SCHEMA, PROMPT_SHA = _load(PROMPT_DIR)
MULT_KEYS = ("fga", "fta", "tpm", "reb", "ast", "stl", "blk", "tov", "fg_pct", "ft_pct")
# Clamp ranges (also stated in the prompt): a typo in the answer must not blow up a line.
MULT_RANGE = (0.6, 1.5)
PCT_RANGE = (0.93, 1.07)
_COMMENT = re.compile(r"<!--.*?-->\s*", re.S)


def _md(path) -> str | None:
    return _COMMENT.sub("", path.read_text(encoding="utf-8")).strip() if path.exists() else None


def _slugs() -> dict[int, str]:
    out = {}
    for p in PLAYER_JSON.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))["player"]
        out[d["pk"]] = d["slug"]
    return out


def _per_game(r, minutes: float | None = None) -> str:
    gp = r.gp or 1.0
    fg = f"{100 * r.fgm / r.fga:.1f} ({r.fga / gp:.1f})" if r.fga else "-"
    ft = f"{100 * r.ftm / r.fta:.1f} ({r.fta / gp:.1f})" if r.fta else "-"
    m = minutes if minutes is not None else r.min
    mpg = f"{m / gp:.1f}" if m else "-"
    vals = " | ".join(f"{getattr(r, c) / gp:.1f}" for c in ("tpm", "pts", "reb", "ast", "stl", "blk", "tov"))
    return f"{r.gp:.0f} | {mpg} | {fg} | {ft} | {vals}"


HEADER = ("| Line | GP | MIN | FG% (FGA) | FT% (FTA) | 3PM | PTS | REB | AST | STL | BLK | TO |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|")


def team_input(db, team: str, season: str = CURRENT_SEASON) -> tuple[str, list[int]]:
    """The user prompt for one team and the player ids in it."""
    players = {p.id: p for p in db.scalars(select(Player).where(Player.team == team))}
    own = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
        PlayerProjection.source == "own-base", PlayerProjection.season == season,
        PlayerProjection.player_pk.in_(list(players))))}
    others = {}
    for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source.in_(("fanscout", "fantrax", "yahoo", "espn", "own-stat")), PlayerProjection.season == season,
            PlayerProjection.player_pk.in_(list(own)))):
        others[(r.player_pk, r.source)] = r
    fpros = {}
    for r in db.scalars(select(PlayerMinutesProjection).where(PlayerMinutesProjection.source == "fantasypros",
                                                              PlayerMinutesProjection.season == season,
                                                              PlayerMinutesProjection.player_pk.in_(list(own)))):
        x, gp = r.extra or {}, (r.extra or {}).get("GP") or 0
        if gp:
            pg = lambda k: f"{x[k] / gp:.1f}" if k in x else "-"  # noqa: E731
            fpros[r.player_pk] = (f"{gp:.0f} | {r.mpg:.1f} | {100 * x.get('FG%', 0):.1f} (-) | {100 * x.get('FT%', 0):.1f} (-) | "
                                  + " | ".join(pg(k) for k in ("3PM", "PTS", "REB", "AST", "STL", "BLK", "TO")))
    last = previous(season)
    past = {}
    for r in db.scalars(select(PlayerSeasonStats).where(
            PlayerSeasonStats.source == "nba", PlayerSeasonStats.season.in_((last, previous(last))),
            PlayerSeasonStats.player_pk.in_(list(own)))):
        past[(r.player_pk, r.season)] = r
    logs = {(pk, s): m for pk, s, m in db.execute(
        select(PlayerGameLog.player_pk, PlayerGameLog.season, func.sum(PlayerGameLog.min))
        .where(PlayerGameLog.season_type == "regular", PlayerGameLog.player_pk.in_(list(own)))
        .group_by(PlayerGameLog.player_pk, PlayerGameLog.season))}
    slugs = _slugs()
    blocks = []
    order = sorted(own, key=lambda pk: -(own[pk].min or 0))
    exp = cd.experience(db)
    inj = cd.injuries(db, season)
    adv = cd.advanced(db, order)
    mins = cd.minutes_sources(db, order, season)
    dch = cd.depth(db, team, season)
    splits = cd.with_without(db, team, order, season)
    darko = cd.darko_rates(db, order, season)
    for pk in order:
        p, o = players[pk], own[pk]
        x = o.extra or {}
        rows = [f"| **Own base: consensus** (minutes: {x.get('minutes')}, games: {x.get('gp_from')}) | {_per_game(o)} |"]
        for src, label in (("yahoo", "Yahoo (weight 2)"), ("fanscout", "FanScout (weight 1)"),
                           ("fantrax", "Fantrax (weight 1)"), ("espn", "ESPN (weight 1)"),
                           ("own-stat", "Own stat model (weight 1)")):
            if (pk, src) in others:
                rows.append(f"| {label} | {_per_game(others[(pk, src)])} |")
        if pk in fpros:
            rows.append(f"| FantasyPros (weight 1) | {fpros[pk]} |")
        for s in (last, previous(last)):
            if (pk, s) in past:
                rows.append(f"| {s} actual | {_per_game(past[(pk, s)], logs.get((pk, s)))} |")
        prof = _md(PLAYER_MD / f"{slugs[pk]}.md") if pk in slugs else None
        years = exp.get(pk)
        bio = [f"NBA seasons before this one: {years if years is not None else 'unknown'}"
               + (" (rookie)" if years == 0 else " (second-year player)" if years == 1 else ""),
               f"Injury status now: {inj.get(pk, 'none listed')}",
               f"Minutes sources: {mins.get(pk, 'none')}",
               f"Depth chart (Hashtag): {dch.get(pk, 'not listed')}",
               f"DARKO skill rates (info only, not in the consensus): {darko.get(pk, 'none')}",
               f"Own GP model (for comparison): {x.get('own_gp_model') or '-'}"]
        extra_blocks = []
        if adv.get(pk):
            extra_blocks += ["Usage and efficiency by season:", "",
                             "| Season | GP | USG% | TS% | AST% | REB% | TOV% |", "|---|---|---|---|---|---|---|",
                             *adv[pk], ""]
        if splits.get(pk):
            extra_blocks += [f"Last season with and without key teammates (games for {team} only):", "", splits[pk], ""]
        blocks.append("\n".join([
            f"### {p.first_name} {p.last_name} (player_id {pk}, {p.position or '-'}, age {x.get('age') or '-'})",
            "", *[f"- {b}" for b in bio], "", HEADER, *rows, "", *extra_blocks,
            "Profile:" if prof else "No expert profile.", "", prof or "",
        ]).strip())
    text = USER_PROMPT.format(team=team, today=date.today().isoformat(),
                              team_profile=_md(TEAM_MD / f"{team}.md") or "None.",
                              team_changes=cd.team_changes(db, team, season),
                              sources=cd.sources_summary(db, season),
                              players="\n\n---\n\n".join(blocks))
    return text, order


def _clamp_mult(m: dict | None) -> dict[str, float]:
    out = {}
    for k, v in (m or {}).items():
        if k in MULT_KEYS and isinstance(v, (int, float)):
            lo, hi = PCT_RANGE if k.endswith("_pct") else MULT_RANGE
            v = min(max(float(v), lo), hi)
            if abs(v - 1.0) > 1e-9:
                out[k] = round(v, 3)
    return out


def _scenario(s: dict | None) -> dict:
    if not s:
        return {}
    return {"mpg": s.get("mpg"), "multipliers": _clamp_mult(s.get("multipliers"))}


def system_prompt() -> str:
    return SYSTEM.replace("{knowledge_dir}", str(KNOWLEDGE_DIR)).replace("{inputs_file}", str(INPUTS_FILE))


def write_inputs(db, season: str = CURRENT_SEASON) -> None:
    """League-wide table the LLM can read: own base, ESPN, Yahoo and last season per game."""
    import csv

    players = {p.id: p for p in db.scalars(select(Player))}
    proj = {}
    for r in db.scalars(select(PlayerProjection).where(PlayerProjection.season == season,
                                                       PlayerProjection.source.in_(("own", "espn", "yahoo")))):
        proj[(r.player_pk, r.source)] = r
    last = {r.player_pk: r for r in db.scalars(select(PlayerSeasonStats).where(
        PlayerSeasonStats.source == "nba", PlayerSeasonStats.season == previous(season)))}
    cols = ("gp", "mpg", "fg_pct", "fga", "ft_pct", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")

    def pg(r) -> list:
        if r is None or not r.gp:
            return [""] * len(cols)
        g = r.gp
        v = {"gp": g, "mpg": (r.min or 0) / g if r.min else "", "fg_pct": r.fgm / r.fga if r.fga else "",
             "fga": r.fga / g, "ft_pct": r.ftm / r.fta if r.fta else "", "fta": r.fta / g}
        v |= {c: getattr(r, c) / g for c in ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")}
        return [round(v[c], 3) if isinstance(v[c], float) else v[c] for c in cols]

    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with INPUTS_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        head = ["player_id", "name", "team", "position", "minutes_source"]
        for pre in ("own", "espn", "yahoo", "last"):
            head += [f"{pre}_{c}" for c in cols]
        w.writerow(head)
        pks = sorted({pk for pk, _ in proj}, key=lambda pk: -((proj.get((pk, "own")) or proj.get((pk, "espn"))
                                                               or proj.get((pk, "yahoo"))).pts or 0))
        for pk in pks:
            p, own = players[pk], proj.get((pk, "own"))
            w.writerow([pk, f"{p.first_name} {p.last_name}", p.team or "FA", p.position or "",
                        (own.extra or {}).get("minutes", "") if own else "",
                        *pg(own), *pg(proj.get((pk, "espn"))), *pg(proj.get((pk, "yahoo"))), *pg(last.get(pk))])


MAX_AGE_DAYS = 7  # a team's context layer is redone at least weekly


def knowledge_sha(db, team: str, season: str = CURRENT_SEASON) -> str:
    """Hash of what the experts and the roster say about a team: the team profile, the profiles of
    every player on the NBA.com roster, and the roster itself. Source numbers change every day and
    are not in it (the base absorbs them for free); a new note or a roster move changes it."""
    import hashlib

    players = sorted(db.scalars(select(Player).where(Player.team == team)), key=lambda p: p.id)
    slugs = _slugs()
    parts = [str([p.id for p in players]), _md(TEAM_MD / f"{team}.md") or ""]
    parts += [_md(PLAYER_MD / f"{slugs[p.id]}.md") or "" for p in players if p.id in slugs]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def why_stale(db, team: str, season: str = CURRENT_SEASON) -> str | None:
    """Why a team's context layer must run again, or None when it is current."""
    path = OUT_DIR / f"{team}.json"
    if not path.exists():
        return "never run"
    doc = json.loads(path.read_text())
    if doc.get("prompt_version") != CONFIG["prompt_version"]:
        return f"prompt v{doc.get('prompt_version')} -> v{CONFIG['prompt_version']}"
    if doc.get("knowledge_sha") != knowledge_sha(db, team, season):
        return "expert notes or roster changed"
    age = datetime.now(UTC) - datetime.fromisoformat(doc["built_at"])
    if age.days >= MAX_AGE_DAYS:
        return f"{age.days} days old"
    return None


def run_team(db, team: str, season: str = CURRENT_SEASON) -> dict:
    prompt, ids = team_input(db, team, season)
    raw, usage = llm.run_json(prompt, system_prompt(), SCHEMA, model=CONFIG["model"], effort=CONFIG["effort"],
                              timeout=2400, read_dirs=[str(KNOWLEDGE_DIR), str(INPUTS_DIR)])
    raw = no_em_dash(raw)
    doc = {"team": team, "season": season, "prompt_version": CONFIG["prompt_version"], "prompt_sha": PROMPT_SHA,
           "knowledge_sha": knowledge_sha(db, team, season),
           "built_at": datetime.now(UTC).isoformat(timespec="seconds"), "llm": usage, **raw}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{team}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    known = set(ids)
    got = [p for p in raw["players"] if p["player_id"] in known]
    doc["missing"] = sorted(known - {p["player_id"] for p in got})
    doc["unknown"] = [p["player_id"] for p in raw["players"] if p["player_id"] not in known]
    now = datetime.now(UTC).replace(tzinfo=None)
    db.execute(delete(ProjectionAdjustment).where(
        ProjectionAdjustment.source == "llm", ProjectionAdjustment.season == season,
        ProjectionAdjustment.player_pk.in_(ids)))
    for p in got:
        db.add(ProjectionAdjustment(
            player_pk=p["player_id"], season=season, source="llm",
            usg=p.get("usg"), mpg=p.get("mpg"), gp=p.get("gp"), games_out=p.get("games_out"), late_games_out=p.get("late_games_out"),
            multipliers=_clamp_mult(p.get("multipliers")), floor=_scenario(p.get("floor")),
            ceiling=_scenario(p.get("ceiling")), reasons=p.get("reasons") or [],
            note=p.get("summary"), model=f"v{CONFIG['prompt_version']}-{PROMPT_SHA}", updated_at=now))
    return doc
