"""Own projection (T-025), base layer: fit, backtest, write.

  fit       fit the parameters on all past seasons, save to data/projection_params.json
  backtest  fit on seasons before 2025-26 only, project 2025-26 with ESPN's 2025-26 preseason
            minutes, compare with ESPN's own 2025-26 projection against the real season;
            writes docs/modules/projection-backtest.md
  run       project 2026-27 for every player with a minutes projection; writes
            player_projections source "own" (plus "own-floor", "own-ceiling" later)

Run: make projection ARGS=fit|backtest|run
"""

import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

from sqlalchemy import delete, func, select

from app.analytics.projection import consensus, fit
from app.analytics.projection.data import FIELDS, load_history, season_age
from app.analytics.projection.engine import Params, Season, project, project_gp, rates
from app.analytics.valuation import Settings, run as value_run
from app.config import DATA_DIR
from app.db import SessionLocal, init_db
from app.models import Player, PlayerAdvancedStats, PlayerGameLog, PlayerMinutesProjection, PlayerProjection, PlayerSeasonStats, ProjectionAdjustment
from app.seasons import CURRENT_SEASON, previous

PARAMS_FILE = DATA_DIR / "projection_params.json"
OUT = Path(__file__).resolve().parents[3] / "docs" / "modules" / "projection-backtest.md"
TEST = "2025-26"
CATS = ("fg_pct", "ft_pct", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def save_params(p: Params, note: dict) -> None:
    d = asdict(p)
    d["age"] = {c: {str(a): f for a, f in curve.items()} for c, curve in p.age.items()}
    PARAMS_FILE.write_text(json.dumps({"params": d, "note": note}, indent=1))


def load_params() -> Params:
    d = json.loads(PARAMS_FILE.read_text())["params"]
    d["season_weights"] = tuple(d["season_weights"])
    d["age"] = {c: {int(a): f for a, f in curve.items()} for c, curve in d["age"].items()}
    return Params(**d)


def fitted(data, positions, targets: list[str]) -> tuple[Params, dict]:
    case_list = fit.cases(data, positions, targets)
    p, report = fit.fit_rates(case_list)
    a, b, shift = fit.fit_gp(data, targets, p.season_weights)
    train = {s: ss for s, ss in ((pk, {k: v for k, v in ss.items() if k <= max(targets)}) for pk, ss in data.items())}
    p = replace(p, gp_a=a, gp_b=b, gp_shift=shift, age=fit.fit_age(train))
    return p, {"targets": targets, "cases": len(case_list), "weights": {str(k): v["score"] for k, v in report.items()}}


def cmd_fit() -> None:
    with SessionLocal() as db:
        data, positions, births = load_history(db)
    seasons = sorted({s for ss in data.values() for s in ss})
    p, note = fitted(data, positions, seasons[1:])
    note["births"] = len(births)
    save_params(p, note)
    print(f"seasons {seasons}, cases {note['cases']}, birth dates {len(births)}")
    print(f"weights {p.season_weights}  K {p.k}  GP share = {p.gp_a:.3f} + {p.gp_b:.3f} x past + {p.gp_shift:.3f} (median shift)")
    print(f"saved {PARAMS_FILE}")


def per_game(line: dict) -> dict[str, float]:
    gp = line["gp"] or 1.0
    out = {c: line[c] / gp for c in ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")}
    out["fg_pct"] = line["fgm"] / line["fga"] if line["fga"] else 0.0
    out["ft_pct"] = line["ftm"] / line["fta"] if line["fta"] else 0.0
    return out


def cmd_backtest() -> None:
    with SessionLocal() as db:
        data, positions, _ = load_history(db)
        espn = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "espn", PlayerProjection.season == TEST))}
        actual = {r.player_pk: r for r in db.scalars(select(PlayerSeasonStats).where(
            PlayerSeasonStats.source == "nba", PlayerSeasonStats.season == TEST))}
    seasons = sorted({s for ss in data.values() for s in ss if s < TEST})
    p, note = fitted(data, positions, seasons[1:])
    # Priors from the seasons before TEST.
    past = [(s, positions.get(pk)) for pk, ss in data.items() for k, s in ss.items() if k < TEST]
    priors = fit.priors_by_position([s for s, _ in past], [x for _, x in past])

    rows = []  # (pk, ours line, espn line, actual line)
    for pk, e in espn.items():
        if not e.gp or not e.min or pk not in actual or pk not in data:
            continue
        hist = fit.history_before(data[pk], TEST, len(p.season_weights))
        if not hist:
            continue
        a = actual[pk]
        a_min = data[pk].get(TEST).min if TEST in data[pk] else None
        if not a_min or a_min < fit.MIN_MINUTES:
            continue
        r = rates(hist, fit.prior_for(priors, positions.get(pk)), p)
        ours = project(r, e.min / e.gp, e.gp, hist[0].age + 1 if hist[0].age else None, p)
        ours_gp = project_gp(hist, p)
        rows.append((pk, ours, {f: getattr(e, f) for f in ("gp", *FIELDS, "pts")},
                     {f: getattr(a, f) for f in ("gp", *FIELDS, "pts")}, ours_gp))

    def mae(which: int) -> dict[str, float]:
        out = {}
        for c in CATS:
            errs, ws = [], []
            for row in rows:
                pg, act = per_game(row[which]), per_game(row[3])
                w = row[3]["fga"] if c == "fg_pct" else row[3]["fta"] if c == "ft_pct" else 1.0
                errs.append(abs(pg[c] - act[c]) * w)
                ws.append(w)
            out[c] = sum(errs) / sum(ws)
        return out

    m_ours, m_espn = mae(1), mae(2)
    gp_ours = fmean(abs(r[4] - r[3]["gp"]) for r in rows)
    gp_espn = fmean(abs(r[2]["gp"] - r[3]["gp"]) for r in rows)
    # All players with an ESPN preseason GP and a past season; no real row = 0 games.
    gp_all = []
    for pk, e in espn.items():
        if not e.gp or pk not in data:
            continue
        hist = fit.history_before(data[pk], TEST, len(p.season_weights))
        if hist:
            real_gp = actual[pk].gp if pk in actual else 0.0
            gp_all.append((abs(project_gp(hist, p) - real_gp), abs(e.gp - real_gp)))

    # Value ranks: Minus-1 per game, top 150 by real value, Spearman with each projection.
    def ranks(which: int) -> dict:
        res = value_run({r[0]: {k: v for k, v in r[which].items() if k != "min"} for r in rows},
                        "minus1", Settings(basis="per_game"))
        return {pk: v["rank"] for pk, v in res.items()}

    real, r_ours, r_espn = ranks(3), ranks(1), ranks(2)
    top = [pk for pk, rk in real.items() if rk <= 150]

    def spearman(pred: dict) -> float:
        xs = sorted(top, key=lambda pk: pred[pk])
        ys = sorted(top, key=lambda pk: real[pk])
        rx = {pk: i for i, pk in enumerate(xs)}
        ry = {pk: i for i, pk in enumerate(ys)}
        n = len(top)
        return 1 - 6 * sum((rx[pk] - ry[pk]) ** 2 for pk in top) / (n * (n * n - 1))

    lines = [
        "# Projection backtest (T-025, base layer)",
        "",
        f"Generated by `make projection ARGS=backtest` on {datetime.now(UTC):%Y-%m-%d}. Do not edit.",
        "",
        f"Test season {TEST}. Parameters fitted on target seasons {note['targets']} only (no {TEST} data).",
        f"Both projections use ESPN's {TEST} preseason minutes per game, so this compares per-minute rates and",
        "shooting, not the minutes forecast. GP is compared separately.",
        f"Players: {len(rows)} with an ESPN preseason projection, a past season and at least {fit.MIN_MINUTES} real minutes.",
        "",
        f"Fitted: season weights {p.season_weights}, K {p.k}, GP share = {p.gp_a:.3f} + {p.gp_b:.3f} x past share.",
        "",
        "## Per game mean absolute error (lower is better)",
        "",
        "FG% and FT% errors are weighted by the player's real attempts.",
        "",
        "| | " + " | ".join(CATS) + " |",
        "|---|" + "---|" * len(CATS),
        "| Own base | " + " | ".join(f"{m_ours[c]:.3f}" for c in CATS) + " |",
        "| ESPN | " + " | ".join(f"{m_espn[c]:.3f}" for c in CATS) + " |",
        "",
        "## Games played, mean absolute error",
        "",
        f"Players above: own GP model {gp_ours:.1f} games, ESPN {gp_espn:.1f} games. This sample has only",
        f"players with {fit.MIN_MINUTES}+ real minutes, so it leaves out season-long injuries and busts.",
        f"All {len(gp_all)} players with an ESPN preseason GP and a past season (no real row = 0 games):",
        f"own {fmean(a for a, _ in gp_all):.1f} games, ESPN {fmean(b for _, b in gp_all):.1f} games.",
        "Known injuries at season start are not in the own GP model yet (adjustment layer).",
        "",
        "## Value rank (Minus-1, per game), Spearman vs the real top 150",
        "",
        f"Own base {spearman(r_ours):.3f}. ESPN {spearman(r_espn):.3f}.",
        "",
    ]
    OUT.write_text("\n".join(lines))
    print("\n".join(lines))


SEASON = CURRENT_SEASON


def merged_adjustments(db, season: str) -> dict[int, dict]:
    """Per player: llm values, then manual values on top (field by field, multipliers key by key)."""
    out: dict[int, dict] = {}
    rows = db.scalars(select(ProjectionAdjustment).where(ProjectionAdjustment.season == season))
    for a in sorted(rows, key=lambda a: a.source != "llm"):  # llm first, manual overrides
        m = out.setdefault(a.player_pk, {"multipliers": {}, "sources": []})
        for f in ("mpg", "gp", "games_out", "late_games_out"):
            if getattr(a, f) is not None:
                m[f] = getattr(a, f)
        m["multipliers"].update(a.multipliers or {})
        for f in ("floor", "ceiling"):
            if getattr(a, f):
                m[f] = getattr(a, f)
        m["sources"].append(a.source)
    return out


def minutes_chain(db, season: str, data) -> dict[int, tuple[float, str]]:
    """Projected minutes per game and where they came from: ESPN, FantasyPros, last season
    (10+ games), DARKO. The user trusts ESPN most and DARKO least (2026-10-05)."""
    out: dict[int, tuple[float, str]] = {}
    darko, fpros = {}, {}
    for r in db.scalars(select(PlayerMinutesProjection).where(PlayerMinutesProjection.season == season)):
        (darko if r.source == "darko" else fpros if r.source == "fantasypros" else {})[r.player_pk] = r.mpg
    espn = {r.player_pk: r.min / r.gp for r in db.scalars(select(PlayerProjection).where(
        PlayerProjection.source == "espn", PlayerProjection.season == season)) if r.min and r.gp}
    last = previous(season)
    lastm = {pk: ss[last].min / ss[last].gp for pk, ss in data.items() if last in ss and ss[last].gp >= 10}
    for name, src in (("darko", darko), ("last season", lastm), ("fantasypros", fpros), ("espn", espn)):
        for pk, v in src.items():
            if v and v > 0:
                out[pk] = (v, name)  # later sources in this loop win
    return out


def cmd_run() -> None:
    p = load_params()
    with SessionLocal() as db:
        data, positions, births = load_history(db)
        minutes = minutes_chain(db, SEASON, data)
        adj = merged_adjustments(db, SEASON)
        espn = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "espn", PlayerProjection.season == SEASON))}
        yahoo = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "yahoo", PlayerProjection.season == SEASON))}
        fantrax = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "fantrax", PlayerProjection.season == SEASON))}
        fanscout = {r.player_pk: r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "fanscout", PlayerProjection.season == SEASON))}
        fpros = {}
        for r in db.scalars(select(PlayerMinutesProjection).where(
                PlayerMinutesProjection.source == "fantasypros", PlayerMinutesProjection.season == SEASON)):
            x = r.extra or {}
            gp = x.get("GP") or 0
            if gp:  # totals and percentages, no attempts (see app/sources/roles/fantasypros.py)
                fpros[r.player_pk] = {"mpg": r.mpg, "fg_pct": x.get("FG%"), "ft_pct": x.get("FT%"),
                                      **{c: x[k] / gp for c, k in (("tpm", "3PM"), ("reb", "REB"), ("ast", "AST"),
                                                                    ("stl", "STL"), ("blk", "BLK"), ("tov", "TO")) if k in x}}
        teams = {pk: t for pk, t in db.execute(select(Player.id, Player.team))}
    past = [(s, positions.get(pk)) for pk, ss in data.items() for s in ss.values()]
    priors = fit.priors_by_position([s for s, _ in past], [x for _, x in past])

    # Rookies have no GP history. ESPN gives every healthy player about 76 to 78 games, more than
    # the median season, so scale ESPN's GP by the median ratio own / ESPN of the veterans.
    ratios = []
    for pk, e in espn.items():
        hist = fit.history_before(data.get(pk, {}), SEASON, len(p.season_weights))
        if hist and e.gp:
            ratios.append(project_gp(hist, p) / e.gp)
    espn_gp_ratio = sorted(ratios)[len(ratios) // 2] if ratios else 1.0

    # Universe: a current team or an outside projection, and some minutes.
    pks = [pk for pk in set(minutes) | set(fantrax) | set(fanscout) | set(fpros)
           if (teams.get(pk) or pk in espn or pk in fantrax or pk in fanscout)
           and (pk in minutes or pk in fantrax or pk in fanscout or pk in fpros)]
    now = datetime.now(UTC).replace(tzinfo=None)
    rows, counts = [], {"history": 0, "espn": 0, "prior": 0}
    for pk in pks:
        a = adj.get(pk, {"multipliers": {}, "sources": []})
        hist = fit.history_before(data.get(pk, {}), SEASON, len(p.season_weights))
        e = espn.get(pk)
        if hist:
            rates_from = "history"
        elif e and e.min and e.gp:
            # No NBA season yet (rookie): ESPN's line stands in for one season of history.
            hist = [Season(season=SEASON, gp=e.gp, min=e.min, stats={f: getattr(e, f) for f in FIELDS})]
            rates_from = "espn"
        else:
            rates_from = "prior"
        counts[rates_from] += 1
        stat_rates = rates(hist, fit.prior_for(priors, positions.get(pk)), p)
        age = season_age(births.get(pk), SEASON)
        # Base v2 (user, 2026-10-05): weighted consensus of the outside projections and our stat model.
        lines = {src: consensus.per_game({f: getattr(row, f) for f in ("gp", "min", *FIELDS, "pts")})
                 for src, row in (("fanscout", fanscout.get(pk)), ("fantrax", fantrax.get(pk)),
                                         ("yahoo", yahoo.get(pk)), ("espn", e)) if row}
        if pk in fpros:
            lines["fantasypros"] = fpros[pk]
        lines = {k: v for k, v in lines.items() if v}
        base_mpg = consensus.consensus_minutes(lines)
        mpg_from = "consensus" if base_mpg else None
        if base_mpg is None:
            base_mpg, mpg_from = minutes.get(pk, (0.0, None))
        if rates_from != "prior" and base_mpg:
            # Our stat model at the consensus minutes, aged (the outside lines already include age).
            stat_line = project(stat_rates, base_mpg, 1.0, age, p)
            lines["own-stat"] = consensus.per_game({**stat_line, "gp": 1.0, "min": base_mpg})
        r = consensus.to_rates(consensus.combine(lines), base_mpg, stat_rates) if lines else stat_rates
        r_age = None  # consensus rates are final; no second age factor
        mpg = a.get("mpg", base_mpg)
        adj_mpg_from = "adjustment" if "mpg" in a else mpg_from
        # GP (user, 2026-10-05): Yahoo's projected games first; the context layer lowers it for
        # injury-prone players. Then ESPN on our scale, then our own GP model.
        own_gp = project_gp(hist, p) if rates_from == "history" else None
        y = yahoo.get(pk)
        if y and y.gp:
            base_gp, gp_from = min(y.gp, 82.0), "yahoo"
        elif e and e.gp:
            base_gp, gp_from = min(e.gp * espn_gp_ratio, 82.0), "espn"
        elif own_gp is not None:
            base_gp, gp_from = own_gp, "own model"
        else:
            base_gp, gp_from = project_gp([], p), "pool"
        # The base without any adjustment: what the context layer sees and adjusts.
        if not base_mpg:
            continue
        bl = project(r, base_mpg, base_gp, r_age, p)
        base_extra = {"minutes": mpg_from, "gp_from": gp_from, "rates": rates_from, "age": age,
                      "sources": sorted(lines), "own_gp_model": round(own_gp, 1) if own_gp is not None else None}
        rows.append(PlayerProjection(player_pk=pk, source="own-base", season=SEASON, fetched_at=now,
                                     extra=base_extra, **{k: bl[k] for k in ("gp", "min", *FIELDS, "pts")}))
        if rates_from != "prior":
            sl0 = project(stat_rates, base_mpg, base_gp, age, p)
            rows.append(PlayerProjection(player_pk=pk, source="own-stat", season=SEASON, fetched_at=now,
                                         extra={"minutes": mpg_from, "gp_from": gp_from, "rates": rates_from},
                                         **{k: sl0[k] for k in ("gp", "min", *FIELDS, "pts")}))
        if "gp" in a:  # the context layer or the user sets the season's games directly
            base_gp = a["gp"]
        gp = max(base_gp - a.get("games_out", 0.0) - a.get("late_games_out", 0.0), 0.0)
        line = project(r, mpg, gp, r_age, p, a["multipliers"])
        extra = {"minutes": adj_mpg_from, "mpg": round(mpg, 1), "rates": rates_from, "age": age, "sources": sorted(lines),
                 "base_gp": round(base_gp, 1), "gp_from": gp_from,
                 "own_gp_model": round(own_gp, 1) if own_gp is not None else None, "games_out": a.get("games_out"),
                 "late_games_out": a.get("late_games_out"), "adjustments": a["sources"]}
        rows.append(PlayerProjection(player_pk=pk, source="own", season=SEASON, fetched_at=now,
                                     extra=extra, **{k: line[k] for k in ("gp", "min", *FIELDS, "pts")}))
        for name in ("floor", "ceiling"):
            # Scenarios are about performance per game (user, 2026-10-05): same games as the median.
            sc = a.get(name)
            if not sc or sc.get("mpg") is None or not gp:
                continue
            sl = project(r, sc["mpg"], gp, r_age, p, sc.get("multipliers") or {})
            rows.append(PlayerProjection(player_pk=pk, source=f"own-{name}", season=SEASON, fetched_at=now,
                                         extra={"scenario": name, **sc},
                                         **{k: sl[k] for k in ("gp", "min", *FIELDS, "pts")}))
    with SessionLocal.begin() as db:
        db.execute(delete(PlayerProjection).where(
            PlayerProjection.source.in_(("own", "own-base", "own-stat", "own-floor", "own-ceiling")), PlayerProjection.season == SEASON))
        db.add_all(rows)
    src, nsrc = {}, {}
    for row in rows:
        if row.source == "own-base":
            src[row.extra["minutes"]] = src.get(row.extra["minutes"], 0) + 1
            k = len(row.extra["sources"])
            nsrc[k] = nsrc.get(k, 0) + 1
    print(f"ESPN GP ratio for rookies {espn_gp_ratio:.3f}.")
    print(f"own {SEASON}: {sum(src.values())} players ({len(rows)} rows). Minutes from {src}. "
          f"Sources per player {dict(sorted(nsrc.items()))}. Stat model rates from {counts}.")


def cmd_context(teams: list[str], only_stale: bool = False) -> None:
    """Context layer for the given teams (or all 30), then `run` again. Prints progress.
    only_stale: only the teams whose expert notes or roster changed, whose prompt version is
    old, or whose last run is a week old (see context.why_stale)."""
    import time

    from app.analytics.projection import context
    from app.sources.teams import canonical

    with SessionLocal() as db:
        all_teams = sorted({t for (t,) in db.execute(select(Player.team).where(Player.team.is_not(None)))})
    todo = [canonical(t) for t in teams] if teams else all_teams
    from app.jobs import refresh

    print("Checking sources (fetching only the stale ones)...", flush=True)
    for r in refresh.run_stale():
        print(f"  {r.job}: {'ok' if r.ok else 'FAILED'}: {r.message}", flush=True)
    with SessionLocal() as db:
        table = refresh.status_table(db)
    print(table, flush=True)
    if "STALE" in table:
        print("WARNING: a manual source is older than a week (see above). Continuing.", flush=True)
    print("Rebuilding the base from the newest source data...", flush=True)
    cmd_run()  # the LLM must see a base built from today's sources
    if only_stale:
        with SessionLocal() as db:
            reasons = {t: context.why_stale(db, t) for t in todo}
        for t, why in reasons.items():
            print(f"  {t}: {why or 'current, skipped'}", flush=True)
        todo = [t for t, why in reasons.items() if why]
        if not todo:
            print("All teams are current. Nothing to run.")
            return
    with SessionLocal() as db:
        context.write_inputs(db)
    total = 0.0
    for i, team in enumerate(todo, 1):
        with SessionLocal() as db:
            text, ids = context.team_input(db, team)
        print(f"[{i}/{len(todo)}] {team}: started {datetime.now():%H:%M:%S}, {len(ids)} players, "
              f"{len(text.split())} words. One LLM call, usually 3 to 8 minutes...", flush=True)
        t0 = time.time()
        with SessionLocal.begin() as db:
            doc = context.run_team(db, team)
        changed = sum(1 for x in doc["players"] if x.get("mpg") is not None or x.get("games_out")
                      or x.get("late_games_out") or x.get("multipliers"))
        cost = (doc.get("llm") or {}).get("cost_usd_list") or 0.0
        total += cost
        print(f"[{i}/{len(todo)}] {team}: done in {time.time() - t0:.0f} s. {changed} of {len(doc['players'])} "
              f"players changed. Minutes total {doc.get('minutes_total')}. Missing {doc['missing'] or 'none'}. "
              f"Cost {cost:.2f} USD list (total {total:.2f}). File reads {(doc.get('llm') or {}).get('turns')} turns, "
              f"{(doc.get('llm') or {}).get('denied')} denied.", flush=True)
    print("Applying adjustments...", flush=True)
    cmd_run()
    print("Review: make projection-review TEAM=" + todo[0])


def cmd_review(team: str) -> None:
    """Base vs adjusted per game, with the reasons, for one team."""
    from app.analytics.projection import context
    from app.sources.teams import canonical

    team = canonical(team)
    doc_path = context.OUT_DIR / f"{team}.json"
    if doc_path.exists():
        doc = json.loads(doc_path.read_text())
        print(f"{team} (built {doc['built_at']})\nTeam note: {doc['team_note']}\nMinutes total: {doc['minutes_total']}\n")
    with SessionLocal() as db:
        names = {pk: f"{f} {l}" for pk, f, l in db.execute(select(Player.id, Player.first_name, Player.last_name)
                                                            .where(Player.team == team))}
        proj = {}
        for r in db.scalars(select(PlayerProjection).where(PlayerProjection.season == SEASON,
                                                           PlayerProjection.player_pk.in_(list(names)))):
            proj[(r.player_pk, r.source)] = r
        adj = {}
        for a in db.scalars(select(ProjectionAdjustment).where(ProjectionAdjustment.season == SEASON,
                                                               ProjectionAdjustment.player_pk.in_(list(names)))):
            adj.setdefault(a.player_pk, []).append(a)
    cols = ("gp", "mpg", "fg_pct", "ft_pct", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")

    def fmt(r) -> str:
        pg = per_game({f: getattr(r, f) for f in ("gp", *FIELDS, "pts")})
        pg["gp"], pg["mpg"] = r.gp, (r.min or 0) / (r.gp or 1)
        return " ".join(f"{pg[c]:6.3f}" if c.endswith("_pct") else f"{pg[c]:5.1f}" for c in cols)

    print("            " + " ".join(f"{c:>6}" if c.endswith("_pct") else f"{c:>5}" for c in cols))
    order = sorted((pk for pk in names if (pk, "own") in proj), key=lambda pk: -(proj[(pk, "own")].min or 0))
    for pk in order:
        print(f"\n{names[pk]}")
        for src, label in (("espn", "ESPN"), ("own", "Own"), ("own-floor", "Floor"), ("own-ceiling", "Ceiling")):
            if (pk, src) in proj:
                print(f"  {label:<9} {fmt(proj[(pk, src)])}")
        for a in adj.get(pk, []):
            bits = []
            if a.mpg is not None:
                bits.append(f"mpg {a.mpg}")
            if a.games_out:
                bits.append(f"games out {a.games_out}")
            if a.late_games_out:
                bits.append(f"late games out {a.late_games_out}")
            if a.multipliers:
                bits.append(" ".join(f"{k} x{v}" for k, v in a.multipliers.items()))
            print(f"  [{a.source}] {'; '.join(bits) or 'no change'}")
            if a.note:
                print(f"    {a.note}")
            for rs in a.reasons or []:
                print(f"    - {rs.get('field')}: {rs.get('text')}")


SUMMARY_COLS = ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def team_summary(team: str, names: dict, proj: dict, adj: dict, usg_hist: dict) -> list[str]:
    """Code-made rotation table: minutes, usage and per-game lines of every player (own), and a
    totals row per team game as a check. A player's share of a team game = his games / 82."""
    from app.analytics.projection import context_data as cd

    rows = sorted((pk for pk in names if (pk, "own") in proj and proj[(pk, "own")].gp),
                  key=lambda pk: -(proj[(pk, "own")].min or 0) / proj[(pk, "own")].gp)
    out = ["## Team projection (code)", "",
           "Own line per player, sorted by minutes. USG% = the LLM's projected usage (last season in brackets).", "",
           "| Player | GP | MIN | USG% | FG% (FGA) | FT% (FTA) | 3PM | PTS | REB | AST | STL | BLK | TO |",
           "|---|" + "---|" * 12]
    tot = {k: 0.0 for k in ("min", "fga", "fgm", "fta", "ftm", *SUMMARY_COLS)}
    usg_min = 0.0
    for pk in rows:
        r = proj[(pk, "own")]
        g = r.gp
        share = g / 82
        llm_usg = next((a.usg for a in adj.get(pk, []) if a.usg is not None), None)
        last = usg_hist.get(pk, [(None, None)])[0][1]
        usg = (f"{llm_usg:.1f}" if llm_usg is not None else "-") + (f" ({100 * last:.1f})" if last is not None else "")
        mpg = (r.min or 0) / g
        if llm_usg is not None:
            usg_min += llm_usg * mpg * share
        for k in tot:
            tot[k] += (r.min or 0) / g * share if k == "min" else getattr(r, k) / g * share
        fg = f"{100 * r.fgm / r.fga:.1f} ({r.fga / g:.1f})" if r.fga else "-"
        ft = f"{100 * r.ftm / r.fta:.1f} ({r.fta / g:.1f})" if r.fta else "-"
        out.append(f"| {names[pk]} | {g:.0f} | {mpg:.1f} | {usg} | {fg} | {ft} | "
                   + " | ".join(f"{getattr(r, c) / g:.1f}" for c in SUMMARY_COLS) + " |")
    fg = f"{100 * tot['fgm'] / tot['fga']:.1f} ({tot['fga']:.1f})" if tot["fga"] else "-"
    ft = f"{100 * tot['ftm'] / tot['fta']:.1f} ({tot['fta']:.1f})" if tot["fta"] else "-"
    out.append(f"| **Total per team game** | | **{tot['min']:.0f}** | **{usg_min / 48:.0f}** | {fg} | {ft} | "
               + " | ".join(f"**{tot[c]:.1f}**" for c in SUMMARY_COLS) + " |")
    last = cd.team_last_season(team)
    if last:
        lfg = f"{100 * last['fgm'] / last['fga']:.1f} ({last['fga']:.1f})"
        lft = f"{100 * last['ftm'] / last['fta']:.1f} ({last['fta']:.1f})"
        out.append(f"| {team} {previous(SEASON)} actual, per game | | {last['min']:.0f} | | {lfg} | {lft} | "
                   + " | ".join(f"{last[c]:.1f}" for c in SUMMARY_COLS) + " |")
    out += ["", "Checks: minutes should be about 240 per team game. USG% total = sum of usage x minutes / 48, "
            "about 100 when the usage numbers fit together (players without a projected usage count as 0). "
            "Each player's line counts by his share of the 82 games, so injuries and DNPs lower the totals; "
            "the gap to 240 minutes is played by players not on the list or by fill-ins.", ""]
    return out


def review_md(team: str) -> Path:
    """The same review as cmd_review, as a markdown file (tables, readable on a phone)."""
    from app.analytics.projection import context
    from app.sources.teams import canonical

    team = canonical(team)
    doc = json.loads((context.OUT_DIR / f"{team}.json").read_text())
    with SessionLocal() as db:
        names = {pk: f"{f} {l}" for pk, f, l in db.execute(select(Player.id, Player.first_name, Player.last_name)
                                                            .where(Player.team == team))}
        proj = {(r.player_pk, r.source): r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.season == SEASON, PlayerProjection.player_pk.in_(list(names))))}
        adj = {}
        for a in db.scalars(select(ProjectionAdjustment).where(ProjectionAdjustment.season == SEASON,
                                                               ProjectionAdjustment.player_pk.in_(list(names)))):
            adj.setdefault(a.player_pk, []).append(a)
        actual = {r.player_pk: r for r in db.scalars(select(PlayerSeasonStats).where(
            PlayerSeasonStats.source == "nba", PlayerSeasonStats.season == previous(SEASON),
            PlayerSeasonStats.player_pk.in_(list(names))))}
        minutes_last = {pk: m for pk, m in db.execute(
            select(PlayerGameLog.player_pk, func.sum(PlayerGameLog.min)).where(
                PlayerGameLog.season == previous(SEASON), PlayerGameLog.season_type == "regular",
                PlayerGameLog.player_pk.in_(list(names))).group_by(PlayerGameLog.player_pk))}
        usg_hist = {}
        for r in db.scalars(select(PlayerAdvancedStats).where(
                PlayerAdvancedStats.source == "nba", PlayerAdvancedStats.player_pk.in_(list(names)))
                .order_by(PlayerAdvancedStats.season.desc())):
            if r.usg_pct is not None:
                usg_hist.setdefault(r.player_pk, []).append((r.season, r.usg_pct))
    llm_info = doc.get("llm") or {}
    from app.analytics.projection import context_data as cd
    with SessionLocal() as db:
        sources_md = cd.sources_summary(db)
    out = [f"# {team}: projection review", "",
           f"Built {doc['built_at']}. Cost {llm_info.get('cost_usd_list') or 0:.2f} USD list, "
           f"{llm_info.get('turns')} turns, {round((llm_info.get('duration_ms') or 0) / 60000, 1)} min.", "",
           f"Prompt v{doc.get('prompt_version')}.", "",
           "## Sources behind the base", "",
           "Own base = weighted mean per stat of these projections (over the sources that have the player). "
           "Games from Yahoo. Own = own base judged by the LLM context layer.", "",
           sources_md, "",
           *team_summary(team, names, proj, adj, usg_hist),
           f"**Team note (LLM).** {doc['team_note']}", "", f"Minutes total (LLM): {doc['minutes_total']}", ""]
    order = sorted((pk for pk in names if (pk, "own") in proj), key=lambda pk: -(proj[(pk, "own")].min or 0))
    for pk in order:
        out += [f"## {names[pk]}", ""]
        out += ["| | GP | MIN | FG% (FGA) | FT% (FTA) | 3PM | PTS | REB | AST | STL | BLK | TO |", "|---|" + "---|" * 11]
        lines = [(label, proj.get((pk, src))) for src, label in (
            ("yahoo", "Yahoo"), ("espn", "ESPN"), ("own-base", "Own base"), ("own", "**Own**"),
            ("own-floor", "Floor"), ("own-ceiling", "Ceiling"))]
        lines.append((f"{previous(SEASON)} actual", actual.get(pk)))
        for label, r in lines:
            if r is None or not r.gp:
                continue
            pg = per_game({f: getattr(r, f) for f in ("gp", *FIELDS, "pts")})
            m = minutes_last.get(pk) if label.endswith("actual") else r.min  # Yahoo has no minutes
            mpg = f"{m / r.gp:.1f}" if m else "-"
            out.append(f"| {label} | {r.gp:.0f} | {mpg} | {100 * pg['fg_pct']:.1f} ({r.fga / r.gp:.1f}) | "
                       f"{100 * pg['ft_pct']:.1f} ({r.fta / r.gp:.1f}) | "
                       + " | ".join(f"{pg[c]:.1f}" for c in ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")) + " |")
        usg_bits = [f"{s_}: {100 * u:.1f}" for s_, u in usg_hist.get(pk, [])]
        llm_usg = next((a.usg for a in adj.get(pk, []) if a.usg is not None), None)
        out += ["", f"USG%: {', '.join(usg_bits) or 'no history'}"
                + (f". **Projected {llm_usg:.1f}**" if llm_usg is not None else ""), ""]
        for a in adj.get(pk, []):
            bits = []
            if a.mpg is not None:
                bits.append(f"mpg {a.mpg}")
            if a.gp is not None:
                bits.append(f"gp {a.gp:g}")
            if a.games_out:
                bits.append(f"games out {a.games_out:g}")
            if a.late_games_out:
                bits.append(f"late games out {a.late_games_out:g}")
            if a.multipliers:
                bits.append(", ".join(f"{k} x{v}" for k, v in a.multipliers.items()))
            out.append(f"*[{a.source}] {'; '.join(bits) or 'no change'}*")
            out.append("")
            if a.note:
                out += [a.note, ""]
            for rs in a.reasons or []:
                out.append(f"- **{rs.get('field')}**: {rs.get('text')}")
            out.append("")
    path = context.OUT_DIR / "review" / f"{team}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def cmd_prompt(team: str) -> None:
    """Write the exact system prompt and one team's user prompt to data/projection_context/ (no LLM call)."""
    from app.analytics.projection import context

    with SessionLocal() as db:
        context.write_inputs(db)
        text, ids = context.team_input(db, team)
    preview = context.OUT_DIR / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    sys_path, user_path = preview / "system_prompt.md", preview / f"user_prompt_{team}.md"
    sys_path.write_text(context.system_prompt(), encoding="utf-8")
    user_path.write_text(text, encoding="utf-8")
    print(f"System prompt: {sys_path} ({len(context.system_prompt().split())} words)")
    print(f"User prompt:   {user_path} ({len(ids)} players, {len(text.split())} words)")
    print(f"League table:  {context.INPUTS_FILE}")


if __name__ == "__main__":
    init_db()
    args = sys.argv[1:] or ["fit"]
    cmd, rest = args[0], args[1:]
    if cmd == "context":
        cmd_context([t for t in rest if not t.startswith("--")], only_stale="--stale" in rest)
    elif cmd == "prompt":
        cmd_prompt(rest[0])
    elif cmd == "review" and rest and rest[0].lower() == "all":
        from app.analytics.projection import context
        teams = sorted(p.stem for p in context.OUT_DIR.glob("*.json"))
        parts = [review_md(t).read_text(encoding="utf-8") for t in teams]
        path = context.OUT_DIR / "review" / "ALL.md"
        path.write_text("\n\n---\n\n".join(parts), encoding="utf-8")
        print(f"{len(teams)} teams. Markdown: {path}")
        from app.analytics.projection import report
        print(f"HTML: {report.write(teams)}")
    elif cmd == "review":
        cmd_review(rest[0])
        print(f"\nMarkdown: {review_md(rest[0])}")
        from app.analytics.projection import report
        from app.sources.teams import canonical
        print(f"HTML: {report.write([canonical(rest[0])])}")
    else:
        {"fit": cmd_fit, "backtest": cmd_backtest, "run": cmd_run}[cmd]()
