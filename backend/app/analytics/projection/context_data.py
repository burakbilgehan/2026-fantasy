"""Extra numbers for the context layer prompt (T-025). Read-only DB queries, markdown out.

- Bio: NBA experience (ESPN roster `experience.years`, latest raw copy), injury status.
- Usage and efficiency history: USG%, TS%, AST%, REB% per past season (stats.nba.com advanced).
- Minutes: every minutes source side by side, and this preseason's games.
- Depth chart slots (Hashtag).
- Team changes: who left (minutes, shots and assists they take with them) and who arrived.
- With / without splits: last season, per 36 minutes, in games with and without each key
  teammate (the team's top usage players last season, also those who left).
"""

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.config import RAW_DIR
from app.models import (DepthChartEntry, Player, PlayerAdvancedStats, PlayerExternalId, PlayerGameLog,
                        PlayerMarketValue, PlayerMinutesProjection, PlayerProjection)
from app.seasons import CURRENT_SEASON, previous

MIN_SPLIT_GAMES = 5
KEY_TEAMMATES = 3


def experience(db) -> dict[int, int]:
    """{player: NBA seasons before this one} from the newest ESPN roster download."""
    files = sorted((RAW_DIR / "espn_bio").glob("*.json"), key=lambda f: f.stat().st_mtime)
    years: dict[str, int] = {}
    for f in reversed(files):
        d = json.loads(f.read_text())
        rosters = d.get("rosters") or {}
        for roster in (rosters.values() if isinstance(rosters, dict) else rosters):
            for a in (roster or {}).get("athletes", []) if isinstance(roster, dict) else []:
                if "experience" in a and a["id"] not in years:
                    years[str(a["id"])] = a["experience"].get("years")
        if years:
            break
    ids = {e: pk for pk, e in db.execute(select(PlayerExternalId.player_pk, PlayerExternalId.external_id)
                                         .where(PlayerExternalId.source == "espn"))}
    # ESPN counts the coming season once a player has NBA games (Flagg, one season played: 2;
    # Jokic, 11 played: 12; rookies: 0; checked 2026-10-05), so subtract one above zero.
    return {ids[e]: max(y - 1, 0) for e, y in years.items() if e in ids and y is not None}


def injuries(db, season: str) -> dict[int, str]:
    out = {}
    for m in db.scalars(select(PlayerMarketValue).where(PlayerMarketValue.season == season,
                                                       PlayerMarketValue.injury.is_not(None))):
        if m.injury in ("NA", ""):
            continue
        text = f"{m.source}: {m.injury}" + (f" ({m.injury_note})" if m.injury_note else "")
        out[m.player_pk] = f"{out[m.player_pk]}; {text}" if m.player_pk in out else text
    return out


def advanced(db, pks: list[int]) -> dict[int, list[str]]:
    rows = defaultdict(list)
    for r in db.scalars(select(PlayerAdvancedStats).where(PlayerAdvancedStats.source == "nba",
                                                         PlayerAdvancedStats.player_pk.in_(pks))
                        .order_by(PlayerAdvancedStats.season.desc())):
        x = r.extra or {}
        pct = lambda v: f"{100 * v:.1f}" if isinstance(v, (int, float)) else "-"  # noqa: E731
        rows[r.player_pk].append(f"| {r.season} | {r.gp:.0f} | {pct(r.usg_pct)} | {pct(r.ts_pct)} | "
                                 f"{pct(x.get('ast_pct'))} | {pct(x.get('reb_pct'))} | {pct(x.get('tm_tov_pct') / 100 if isinstance(x.get('tm_tov_pct'), (int, float)) else None)} |")
    return rows


def minutes_sources(db, pks: list[int], season: str) -> dict[int, str]:
    src = defaultdict(dict)
    labels = {"fanscout": "FanScout", "fantrax": "Fantrax", "espn": "ESPN"}
    for r in db.scalars(select(PlayerProjection).where(PlayerProjection.season == season,
                                                       PlayerProjection.source.in_(list(labels)),
                                                       PlayerProjection.player_pk.in_(pks))):
        if r.min and r.gp:
            src[r.player_pk][labels[r.source]] = r.min / r.gp
    for r in db.scalars(select(PlayerMinutesProjection).where(PlayerMinutesProjection.season == season,
                                                              PlayerMinutesProjection.player_pk.in_(pks))):
        src[r.player_pk]["FantasyPros" if r.source == "fantasypros" else r.source.upper()] = r.mpg
    pre = defaultdict(list)
    for r in db.scalars(select(PlayerGameLog).where(PlayerGameLog.season == season,
                                                    PlayerGameLog.season_type == "preseason",
                                                    PlayerGameLog.player_pk.in_(pks))):
        pre[r.player_pk].append(r.min)
    out = {}
    for pk in pks:
        bits = [f"{k} {v:.1f}" for k, v in src[pk].items()]
        if pre[pk]:
            bits.append(f"preseason so far {len(pre[pk])} games, {sum(pre[pk]) / len(pre[pk]):.1f} mpg")
        out[pk] = ", ".join(bits) or "none"
    return out


def darko_rates(db, pks: list[int], season: str) -> dict[int, str]:
    """DARKO per-100-possession rates (skill estimate, independent of minutes). Not in the consensus:
    DARKO projects the next game, so its minutes and team can be last season's (user, 2026-10-05)."""
    out = {}
    for r in db.scalars(select(PlayerMinutesProjection).where(PlayerMinutesProjection.source == "darko",
                                                              PlayerMinutesProjection.season == season,
                                                              PlayerMinutesProjection.player_pk.in_(pks))):
        x = r.extra or {}
        if "x_pts_100" not in x:
            continue
        f = lambda k, d=1: f"{x[k]:.{d}f}" if isinstance(x.get(k), (int, float)) else "-"  # noqa: E731
        reb = (x.get("x_orb_100") or 0) + (x.get("x_drb_100") or 0)
        out[r.player_pk] = (f"per 100 possessions: {f('x_pts_100')} pts, {reb:.1f} reb, {f('x_ast_100')} ast, "
                            f"{f('x_stl_100')} stl, {f('x_blk_100')} blk, {f('x_tov_100')} to, {f('x_fga_100')} fga, "
                            f"{f('x_fg3a_100')} 3pa, {f('x_fta_100')} fta; FG% {f('x_fg_pct', 3)}, 3P% {f('x_fg3_pct', 3)}, "
                            f"FT% {f('x_ft_pct', 3)} (row date {x.get('date', '-')})")
    return out


def depth(db, team: str, season: str) -> dict[int, str]:
    out = defaultdict(list)
    for r in db.scalars(select(DepthChartEntry).where(DepthChartEntry.season == season, DepthChartEntry.team == team)):
        if r.player_pk:
            out[r.player_pk].append(f"{r.slot} {'starter' if r.depth == 1 else f'tier {r.depth}'}")
    return {pk: ", ".join(v) for pk, v in out.items()}


def last_teams(db, season: str) -> dict[int, str]:
    """{player: team of his last regular season game} in `season`."""
    out = {}
    for pk, team in db.execute(select(PlayerGameLog.player_pk, PlayerGameLog.team)
                               .where(PlayerGameLog.season == season, PlayerGameLog.season_type == "regular")
                               .order_by(PlayerGameLog.game_date)):
        out[pk] = team
    return out


def team_changes(db, team: str, season: str = CURRENT_SEASON) -> str:
    """Markdown: who left and who arrived since last season, with last season's share of the team."""
    last = previous(season)
    logs = list(db.scalars(select(PlayerGameLog).where(PlayerGameLog.season == last, PlayerGameLog.team == team,
                                                       PlayerGameLog.season_type == "regular")))
    if not logs:
        return "No game logs for this team last season."
    tot = defaultdict(lambda: defaultdict(float))
    for g in logs:
        t = tot[g.player_pk]
        t["gp"] += 1
        for f in ("min", "fga", "fta", "ast", "pts", "reb"):
            t[f] += getattr(g, f)
    team_tot = {f: sum(t[f] for t in tot.values()) for f in ("min", "fga", "fta", "ast", "pts", "reb")}
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(list(tot))))}
    now = {p.id: p for p in db.scalars(select(Player).where(Player.team == team))}
    lt = last_teams(db, last)

    def share(t, f):
        return f"{100 * t[f] / team_tot[f]:.0f}%" if team_tot[f] else "-"

    left = sorted((pk for pk in tot if pk not in now), key=lambda pk: -tot[pk]["min"])
    lines = [f"Left since {last} (their share of {team}'s {last} totals):", "",
             "| Player | Now | GP | MPG | MIN share | FGA share | FTA share | AST share | REB share |", "|---|---|---|---|---|---|---|---|---|"]
    for pk in left:
        t, p = tot[pk], players.get(pk)
        if t["min"] < 100 or p is None:
            continue
        lines.append(f"| {p.first_name} {p.last_name} | {p.team or 'FA'} | {t['gp']:.0f} | {t['min'] / t['gp']:.1f} | "
                     f"{share(t, 'min')} | {share(t, 'fga')} | {share(t, 'fta')} | {share(t, 'ast')} | {share(t, 'reb')} |")
    vac = {f: sum(tot[pk][f] for pk in left) / team_tot[f] for f in ("min", "fga", "ast") if team_tot[f]}
    tl = team_last_season(team, season)
    if tl:
        lines = [f"{team} last season per team game (all players): {tl['min']:.0f} min, {tl['fga']:.1f} FGA, "
                 f"{tl['fta']:.1f} FTA, {tl['tpm']:.1f} 3PM, {tl['pts']:.1f} PTS, {tl['reb']:.1f} REB, "
                 f"{tl['ast']:.1f} AST, {tl['tov']:.1f} TO.", ""] + lines
    lines += ["", f"Vacated in total: {100 * vac.get('min', 0):.0f}% of minutes, {100 * vac.get('fga', 0):.0f}% of shots, "
              f"{100 * vac.get('ast', 0):.0f}% of assists.", ""]
    arrived = [pk for pk in now if lt.get(pk) and lt[pk] != team]
    rookies = [pk for pk in now if pk not in lt]
    if arrived:
        lines.append("Arrived from other teams (last season's team): " + ", ".join(
            f"{now[pk].first_name} {now[pk].last_name} ({lt[pk]})" for pk in arrived) + ".")
    if rookies:
        lines.append("No NBA games last season (rookies, returns from a full season out, or new signings): " + ", ".join(
            f"{now[pk].first_name} {now[pk].last_name}" for pk in rookies) + ".")
    return "\n".join(lines)


def with_without(db, team: str, pks: list[int], season: str = CURRENT_SEASON) -> dict[int, str]:
    """Per player: per 36 minutes last season with and without each key teammate (same team only)."""
    last = previous(season)
    logs = list(db.scalars(select(PlayerGameLog).where(PlayerGameLog.season == last, PlayerGameLog.team == team,
                                                       PlayerGameLog.season_type == "regular")))
    by_game = defaultdict(set)
    by_player = defaultdict(list)
    for g in logs:
        if g.min > 0:
            by_game[g.game_id].add(g.player_pk)
            by_player[g.player_pk].append(g)
    adv = {r.player_pk: r.usg_pct or 0 for r in db.scalars(select(PlayerAdvancedStats).where(
        PlayerAdvancedStats.source == "nba", PlayerAdvancedStats.season == last,
        PlayerAdvancedStats.player_pk.in_(list(by_player))))}
    load = {pk: adv.get(pk, 0) * sum(g.min for g in gs) for pk, gs in by_player.items()}
    keys = sorted(load, key=load.get, reverse=True)[:KEY_TEAMMATES]
    names = {p.id: f"{p.first_name} {p.last_name}" for p in db.scalars(select(Player).where(Player.id.in_(keys)))}

    def per36(gs) -> str:
        m = sum(g.min for g in gs)
        if not m:
            return "-"
        f = 36 / m
        fga, fgm = sum(g.fga for g in gs), sum(g.fgm for g in gs)
        fg = f"{100 * fgm / fga:.1f}" if fga else "-"
        return (f"{len(gs)} g, {m / len(gs):.1f} mpg, per 36: {f * sum(g.pts for g in gs):.1f} pts, "
                f"{f * fga:.1f} fga ({fg}%), {f * sum(g.fta for g in gs):.1f} fta, {f * sum(g.tpm for g in gs):.1f} 3pm, "
                f"{f * sum(g.ast for g in gs):.1f} ast, {f * sum(g.reb for g in gs):.1f} reb, {f * sum(g.tov for g in gs):.1f} to")

    out = {}
    for pk in pks:
        gs = by_player.get(pk, [])
        lines = []
        for k in keys:
            if k == pk:
                continue
            w = [g for g in gs if k in by_game[g.game_id]]
            wo = [g for g in gs if k not in by_game[g.game_id]]
            if len(w) >= MIN_SPLIT_GAMES and len(wo) >= MIN_SPLIT_GAMES:
                lines.append(f"- With {names.get(k, k)}: {per36(w)}\n- Without {names.get(k, k)}: {per36(wo)}")
        if lines:
            out[pk] = "\n".join(lines)
    return out


__all__ = ["advanced", "depth", "experience", "injuries", "minutes_sources", "team_changes", "with_without", "Path"]


def sources_summary(db, season: str = CURRENT_SEASON) -> str:
    """Markdown: every source behind the base, with its weight, player count and fetch time (UTC)."""
    from sqlalchemy import func

    from app.analytics.projection.consensus import MINUTE_WEIGHTS, WEIGHTS

    rows = {}
    for src, n, t in db.execute(select(PlayerProjection.source, func.count(), func.max(PlayerProjection.fetched_at))
                                .where(PlayerProjection.season == season).group_by(PlayerProjection.source)):
        rows[src] = (n, t)
    for src, n, t in db.execute(select(PlayerMinutesProjection.source, func.count(),
                                       func.max(PlayerMinutesProjection.fetched_at))
                                .where(PlayerMinutesProjection.season == season)
                                .group_by(PlayerMinutesProjection.source)):
        rows.setdefault(src, (n, t))
    label = {"yahoo": "Yahoo", "fanscout": "FanScout", "fantrax": "Fantrax", "espn": "ESPN",
             "fantasypros": "FantasyPros", "own-stat": "Own stat model", "darko": "DARKO"}
    note = {"fantasypros": "no shot attempts", "yahoo": "no minutes; games come from Yahoo",
            "own-stat": "last 3 seasons, regressed, aged", "darko": "info only (next-game model)",
            "fantrax": "lowered from 2: stale for last season's breakouts"}
    lines = ["| Source | Stat weight | Minutes weight | Players | Fetched (UTC) | Note |", "|---|---|---|---|---|---|"]
    for src in ("yahoo", "fanscout", "fantrax", "espn", "fantasypros", "own-stat", "darko"):
        n, t = rows.get(src, (0, None))
        lines.append(f"| {label[src]} | {WEIGHTS.get(src, 0):g} | {MINUTE_WEIGHTS.get(src, 0):g} | {n} | "
                     f"{t:%Y-%m-%d %H:%M} | {note.get(src, '')} |" if t else
                     f"| {label[src]} | {WEIGHTS.get(src, 0):g} | {MINUTE_WEIGHTS.get(src, 0):g} | 0 | - | {note.get(src, '')} |")
    return "\n".join(lines)


def team_last_season(team: str, season: str = CURRENT_SEASON) -> dict[str, float] | None:
    """The team's per-game totals last season, from the game logs (minutes, shots, counting stats)."""
    from sqlalchemy import func

    from app.db import SessionLocal

    last = previous(season)
    cols = ("min", "fga", "fgm", "fta", "ftm", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
    with SessionLocal() as db:
        games = db.scalar(select(func.count(func.distinct(PlayerGameLog.game_id))).where(
            PlayerGameLog.season == last, PlayerGameLog.team == team, PlayerGameLog.season_type == "regular"))
        if not games:
            return None
        sums = db.execute(select(*[func.sum(getattr(PlayerGameLog, c)) for c in cols]).where(
            PlayerGameLog.season == last, PlayerGameLog.team == team, PlayerGameLog.season_type == "regular")).one()
    return {c: (v or 0) / games for c, v in zip(cols, sums)}
