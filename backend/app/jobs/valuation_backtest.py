"""T-017 backtest: every valuation model on the 2025-26 season. Plan: docs/modules/valuation.md.

1. Every model runs on ESPN's 2025-26 preseason projection and converts to dollars.
2. The same model runs on the real 2025-26 totals. Rank correlation: preseason vs truth.
3. Model dollars vs our league's real 2025-26 auction prices.
4. Weekly H2H: a 13th team per model buys 12 players with 200 USD at the real league
   prices (undrafted players cost 1 USD) and plays every 2025-26 week against the 12 real
   draft rosters. Draft and hold for every team.

Output: docs/modules/valuation-backtest.md. Run: make valuation-backtest
"""

import random
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import fmean, pstdev

from sqlalchemy import select

from app.analytics.h2h_backtest import all_play, best_roster, team_weeks
from app.analytics.valuation import CATEGORIES, Settings, g_weights, run
from app.db import SessionLocal
from app.models import Draft, DraftPick, Player, PlayerExternalId, PlayerGameLog, PlayerProjection, PlayerSeasonStats
from app.sources.players.base import STAT_FIELDS

SEASON = "2025-26"
G_SEASONS = ("2023-24", "2024-25")  # G-score weights only from seasons before the test season
# Assumed: last day of the 2025-26 fantasy playoffs (our 2026-27 league ends on 2027-03-28).
LAST_DAY = date(2026, 3, 29)
OUT = Path(__file__).resolve().parents[3] / "docs" / "modules" / "valuation-backtest.md"

PAPER_G = {"stl": 0.44, "fg_pct": 0.56, "ft_pct": 0.58, "tov": 0.62, "pts": 0.65, "blk": 0.68,
           "reb": 0.69, "tpm": 0.72, "ast": 0.75}
# (label, model key, punt)
VARIANTS = [
    ("Z-score 9-cat", "zscore", ()),
    ("Minus-1", "minus1", ()),
    ("DURANT approx.", "durant", ()),
    ("G-score", "gscore", ()),
    ("Punt FT%", "punt", ("ft_pct",)),
    ("Punt TO", "punt", ("tov",)),
    ("Punt FG%", "punt", ("fg_pct",)),
    ("Punt AST", "punt", ("ast",)),
]
POOLS = (144, 200, 250, None)
BASES = ("totals", "per_game")
DOLLARS = ("plain", "savor")
DEFAULT = dict(basis="totals", pool=200, dollars="plain")
# Bidding noise (assumed): each draw buys at price x U(0.8, 1.25), undrafted players at 1 to 3 USD.
# One roster per model is mostly injury luck; the mean over the draws is the result.
DRAWS = 30


def load(db):
    def season_rows(model, source):
        return {
            r.player_pk: {f: getattr(r, f) for f in STAT_FIELDS}
            for r in db.scalars(select(model).where(model.source == source, model.season == SEASON))
        }

    pre = season_rows(PlayerProjection, "espn")
    actual = season_rows(PlayerSeasonStats, "nba")
    names = {p.id: f"{p.first_name} {p.last_name}" for p in db.scalars(select(Player))}

    draft = db.scalar(select(Draft).where(Draft.kind == "past_league", Draft.season == SEASON))
    yahoo = dict(db.execute(select(PlayerExternalId.external_id, PlayerExternalId.player_pk)
                            .where(PlayerExternalId.source == "yahoo")).all())
    picks = [(yahoo[p.yahoo_player_id], p.team_id, p.price)
             for p in db.scalars(select(DraftPick).where(DraftPick.draft_pk == draft.id))]

    cols = [PlayerGameLog.player_pk, PlayerGameLog.season, PlayerGameLog.game_date, PlayerGameLog.min,
            *(getattr(PlayerGameLog, f) for f in ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"))]
    logs = [dict(zip(["player", "season", "game_date", "min", "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"], r))
            for r in db.execute(select(*cols).where(PlayerGameLog.season_type == "regular",
                                                    PlayerGameLog.season.in_((*G_SEASONS, SEASON))))]
    return pre, actual, names, picks, logs


def player_weeks(logs):
    """player -> Monday of the week -> summed stats, 2025-26 fantasy weeks only."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for g in logs:
        if g["season"] != SEASON or g["game_date"] > LAST_DAY:
            continue
        d = g["game_date"]
        acc = out[g["player"]][date.fromordinal(d.toordinal() - d.weekday())]
        for k in ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"):
            acc[k] += g[k]
    return out


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=v.__getitem__)
        r = [0.0] * len(v)
        for i, j in enumerate(order):
            r[j] = i
        return r
    return pearson(ranks(xs), ranks(ys))


def pearson(xs, ys):
    mx, my = fmean(xs), fmean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) * sx * sy) if sx and sy else 0.0


def main() -> None:
    t0 = time.time()
    with SessionLocal() as db:
        pre, actual, names, picks, logs = load(db)
    gw = g_weights([g for g in logs if g["season"] in G_SEASONS])
    pw = player_weeks(logs)
    weeks = sorted({w for p in pw.values() for w in p})
    price = {pk: pr for pk, _, pr in picks}
    rosters = defaultdict(list)
    for pk, team, _ in picks:
        rosters[team].append(pk)
    real = {t: team_weeks(r, pw, weeks) for t, r in rosters.items()}
    real_scores = {t: all_play(real[t], [real[o] for o in real if o != t], weeks) for t in real}
    real_sorted = sorted((s[0] for s in real_scores.values()), reverse=True)
    opponents = list(real.values())

    def h2h(roster):
        tw = team_weeks(roster, pw, weeks)
        cat, game = all_play(tw, opponents, weeks)
        return cat, game

    rng = random.Random(17)
    draws = [{pk: max(1, round(price[pk] * rng.uniform(0.8, 1.25))) if pk in price else rng.randint(1, 3)
              for pk in set(pre) | set(actual)} for _ in range(DRAWS)]

    def buy(result, prices):
        cands = {pk: (r["dollars"] + 0.01 * r["total"], prices.get(pk, 1)) for pk, r in result.items()}
        return best_roster(cands, 12, 200)

    def h2h_draws(result):
        """Mean and SD over the draws of the cat %, mean match %, the roster of the real prices."""
        scores = [h2h(buy(result, d)) for d in draws]
        cats = [x[0] for x in scores]
        roster = buy(result, price)
        return fmean(cats), pstdev(cats), fmean(x[1] for x in scores), roster, h2h(roster)

    rows, step2, results = [], {}, {}
    for label, key, punt in VARIANTS:
        for basis in BASES:
            for pool in POOLS:
                s = Settings(basis=basis, pool=pool, punt=frozenset(punt), g_weights=gw)
                act = run(actual, key, s)
                for dollars in DOLLARS:
                    res = run(pre, key, s, dollars=dollars)
                    results[(label, basis, pool, dollars)] = res
                    cat, sd, game, roster, one = h2h_draws(res)
                    place = 1 + sum(1 for x in real_sorted if x > cat)
                    rows.append(dict(label=label, basis=basis, pool=pool, dollars=dollars, cat=cat, sd=sd, game=game,
                                     place=place, one=one[0], spent=sum(price.get(p, 1) for p in roster), roster=roster))
                common = [p for p in res if p in act]
                top = sorted(common, key=lambda p: res[p]["rank"])[:200]
                step2[(label, basis, pool)] = (
                    spearman([res[p]["total"] for p in common], [act[p]["total"] for p in common]),
                    spearman([res[p]["total"] for p in top], [act[p]["total"] for p in top]),
                    len(common),
                )
        print(f"{label}: done ({time.time() - t0:.0f} s)", file=sys.stderr)

    hind = run(actual, "zscore", Settings(**{k: DEFAULT[k] for k in ("basis", "pool")}))
    hc, hsd, hg, hind_roster, _ = h2h_draws(hind)
    hind_score = (hc, hg, 1 + sum(1 for x in real_sorted if x > hc), hsd)

    write_report(rows, step2, results, real_scores, hind_score, hind_roster, hind, gw, pre, actual, names, picks, price, weeks)
    print(f"Wrote {OUT} ({time.time() - t0:.0f} s)", file=sys.stderr)


def _pool(p):
    return "all" if p is None else str(p)


def _pct(x):
    return f"{100 * x:.1f}"


def write_report(rows, step2, results, real_scores, hind_score, hind_roster, hind, gw, pre, actual, names, picks, price, weeks):
    L = []
    a = L.append
    no_actual = [p for p in pre if p not in actual or actual[p]["gp"] == 0]
    drafted_no_proj = [pk for pk, _, _ in picks if pk not in pre]
    a("# Valuation backtest, 2025-26 (T-017)\n")
    a("Generated by `make valuation-backtest` (`backend/app/jobs/valuation_backtest.py`). Do not edit by hand.\n")
    a("## Setup")
    a(f"- Base: ESPN 2025-26 preseason projection, {len(pre)} players. Truth: stats.nba.com 2025-26 totals.")
    a(f"- {len(no_actual)} projected players have no 2025-26 games. {len(drafted_no_proj)} of the league's 144 drafted players have no ESPN projection; models cannot buy them.")
    a(f"- Weeks: Monday to Sunday, {weeks[0]} to {weeks[-1]}, {len(weeks)} weeks (assumed; Yahoo week 1 and All-Star week can differ).")
    a("- H2H test: a 13th team per model buys exactly 12 players with 200 USD. Price = the real 2025-26 price in our league; undrafted players cost 1 USD. "
      "The team maximizes the model's preseason dollars. It plays every week against each of the 12 real draft rosters.")
    a("- Draft and hold for all 13 teams: no waivers, no trades, no lineup cap, positions ignored, injured players score 0. Ties count 0.5.")
    a("- Cat %: share of category matchups won. Match %: share of weekly matchups won. Place: where the cat % would rank among the 12 real teams (their cat % is all-play against the other 11).")
    a(f"- One roster per model is mostly injury luck. So every model buys {DRAWS} rosters, each with bidding noise (assumed): price x U(0.8, 1.25), undrafted players 1 to 3 USD. Cat % and match % are means over the draws. SD: spread of the cat % over the draws. One season only.\n")

    a("## G-score weights")
    a("From 2023-24 and 2024-25 game logs only (no look at 2025-26). Pool: top 144 by minutes per season. Paper: arXiv 2307.02188.\n")
    a("| Category | Ours | Paper |")
    a("|---|---|---|")
    for c in sorted(CATEGORIES, key=gw.get):
        a(f"| {c} | {gw[c]:.2f} | {PAPER_G[c]:.2f} |")
    a("")

    a("## 1. H2H result, default settings (totals, pool 200, plain dollars)")
    a("| Model | Cat % | SD | Match % | Place of 13 | Cat % at real prices | Spent at real prices |")
    a("|---|---|---|---|---|---|---|")
    base = [r for r in rows if r["basis"] == DEFAULT["basis"] and r["pool"] == DEFAULT["pool"] and r["dollars"] == DEFAULT["dollars"]]
    for r in sorted(base, key=lambda r: -r["cat"]):
        a(f"| {r['label']} | {_pct(r['cat'])} | {_pct(r['sd'])} | {_pct(r['game'])} | {r['place']} | {_pct(r['one'])} | {r['spent']} |")
    a(f"| Hindsight (z-score on real 2025-26 totals) | {_pct(hind_score[0])} | {_pct(hind_score[3])} | {_pct(hind_score[1])} | {hind_score[2]} | - | {sum(price.get(p, 1) for p in hind_roster)} |")
    best_real = max(real_scores.values())
    worst_real = min(real_scores.values())
    a(f"\nReal teams: best cat % {_pct(best_real[0])}, median {_pct(sorted(s[0] for s in real_scores.values())[6])}, worst {_pct(worst_real[0])}.\n")

    a("## 2. Sensitivity: cat % by basis, pool and dollars")
    a("| Model | " + " | ".join(f"{b} pool {_pool(p)} {d}" for b in BASES for p in POOLS for d in DOLLARS) + " |")
    a("|---|" + "---|" * (len(BASES) * len(POOLS) * len(DOLLARS)))
    idx = {(r["label"], r["basis"], r["pool"], r["dollars"]): r for r in rows}
    for label, _, _ in VARIANTS:
        a(f"| {label} | " + " | ".join(_pct(idx[(label, b, p, d)]["cat"]) for b in BASES for p in POOLS for d in DOLLARS) + " |")
    a("")
    a("Per game as a dollar base ignores projected GP, so the team buys players who miss games. The basis gap measures the value of the projected GP, not the per-game view.\n")
    a("Mean cat % over all models and the other settings:\n")
    a("| Setting | Value | Mean cat % |")
    a("|---|---|---|")
    for name, vals in (("basis", BASES), ("pool", POOLS), ("dollars", DOLLARS)):
        for v in vals:
            a(f"| {name} | {_pool(v) if name == 'pool' else v} | {_pct(fmean(r['cat'] for r in rows if r[name] == v))} |")
    a("")

    a("## 3. Preseason vs truth (same model)")
    a("Spearman rank correlation between the model's value on the preseason projection and on the real totals. "
      "All: every player in both. Top 200: the model's top 200 preseason players.\n")
    a("| Model | Basis | Pool | All | Top 200 | Players |")
    a("|---|---|---|---|---|---|")
    for (label, basis, pool), (r_all, r_top, n) in step2.items():
        if pool == DEFAULT["pool"]:
            a(f"| {label} | {basis} | {_pool(pool)} | {r_all:.2f} | {r_top:.2f} | {n} |")
    a("")

    for label in ("Z-score 9-cat", "G-score"):
        res = results[(label, DEFAULT["basis"], DEFAULT["pool"], DEFAULT["dollars"])]
        a(f"## {'4' if label.startswith('Z') else '5'}. League prices vs model dollars ({label}, default settings)")
        drafted = [(pk, pr) for pk, _, pr in picks if pk in res]
        a("Residual = league price minus model dollars. Positive = the league paid more than the model.\n")
        a("| Price tier | Players | Mean price | Mean model $ | Mean residual | Mean real-season $ |")
        a("|---|---|---|---|---|---|")
        for lo, hi in ((40, 999), (20, 39), (10, 19), (2, 9), (1, 1)):
            t = [(pk, pr) for pk, pr in drafted if lo <= pr <= hi]
            if t:
                a(f"| {lo}-{hi if hi < 999 else '+'} | {len(t)} | {fmean(pr for _, pr in t):.1f} | {fmean(res[pk]['dollars'] for pk, _ in t):.1f} | "
                  f"{fmean(pr - res[pk]['dollars'] for pk, pr in t):+.1f} | {fmean(hind.get(pk, {'dollars': 0})['dollars'] for pk, _ in t):.1f} |")
        a("\nCorrelation of the residual with each category z (positive = the league pays extra for this category):\n")
        resid = [pr - res[pk]["dollars"] for pk, pr in drafted]
        a("| " + " | ".join(CATEGORIES) + " |")
        a("|" + "---|" * len(CATEGORIES))
        a("| " + " | ".join(f"{pearson(resid, [res[pk]['z'][c] for pk, _ in drafted]):+.2f}" for c in CATEGORIES) + " |")
        a("")
        diff = sorted(drafted, key=lambda x: x[1] - res[x[0]]["dollars"])
        a("Largest gaps (real-season $ = z-score dollars on the real 2025-26 totals; GP = real games):\n")
        a("| Player | Price | Model $ | Real-season $ | GP |")
        a("|---|---|---|---|---|")
        for pk, pr in diff[:8] + diff[-8:]:
            a(f"| {names[pk]} | {pr} | {res[pk]['dollars']:.0f} | {hind.get(pk, {'dollars': 0})['dollars']:.0f} | {actual.get(pk, {'gp': 0})['gp']:.0f} |")
        a("")

    best = max((r for r in rows if r["dollars"] == DEFAULT["dollars"] and r["basis"] == DEFAULT["basis"] and r["pool"] == DEFAULT["pool"]), key=lambda r: r["cat"])
    res = results[(best["label"], best["basis"], best["pool"], best["dollars"])]
    a(f"## 6. Rosters bought: {best['label']} (best default model) and hindsight")
    for title, roster, r in ((best["label"], best["roster"], res), ("Hindsight", hind_roster, hind)):
        a(f"\n{title}:\n")
        a("| Player | Price | Model $ | GP | PTS/g | REB/g | AST/g |")
        a("|---|---|---|---|---|---|---|")
        for pk in sorted(roster, key=lambda p: -price.get(p, 1)):
            s = actual.get(pk)
            gp = s["gp"] if s else 0
            per = (lambda k: f"{s[k] / gp:.1f}") if gp else (lambda k: "-")
            a(f"| {names[pk]} | {price.get(pk, 1)} | {r[pk]['dollars']:.0f} | {gp:.0f} | {per('pts')} | {per('reb')} | {per('ast')} |")
    a("")
    OUT.write_text("\n".join(L))


if __name__ == "__main__":
    main()
