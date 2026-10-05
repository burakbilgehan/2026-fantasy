"""Fit the base layer parameters on past seasons (T-025). Pure functions, no DB.

Method: for each target season T, project T from the seasons before it, compare with the
real T. Every parameter is chosen by the smallest error over all target seasons.

- K per component: grid search. Error = minutes-weighted squared error of the per-minute
  rate (or per-attempt rate), players with at least MIN_MINUTES in T.
- Season weights: grid over a few patterns, scored by the summed K-fitted error.
- GP: least squares of T's GP share on the weighted past share. Only players with a T row
  (a player who missed all of T has no row; this biases the GP mean up, inferred small).
- Age: per component, the minutes-weighted mean change of the rate from one season to the
  next, by age at the second season, pooled into buckets and smoothed.
"""

from collections import defaultdict
from dataclasses import replace

from app.analytics.projection.engine import COMPONENTS, PER_ATT, SEASON_GAMES, Params, Season, rate_parts, rates

MIN_MINUTES = 500  # a target season counts only above this (about 7 games of starter minutes)
K_GRID = (0, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400)
WEIGHT_GRID = ((1, 0, 0), (2, 1, 0), (3, 2, 1), (5, 3, 2), (6, 3, 1), (4, 3, 3), (1, 1, 1))
AGE_BUCKETS = ((19, 21), (22, 23), (24, 25), (26, 27), (28, 29), (30, 31), (32, 33), (34, 40))

# Data shape: {player: {season: Season}}, plus a position per player and a prior per (season, position).
History = dict[object, dict[str, Season]]


def pool_prior(rows: list[Season]) -> dict[str, float]:
    """Pooled rate per component (sum of numerators / sum of denominators)."""
    out = {}
    for c in COMPONENTS:
        n = sum(rate_parts(s, c)[0] for s in rows)
        d = sum(rate_parts(s, c)[1] for s in rows)
        out[c] = n / d if d else 0.0
    return out


def priors_by_position(seasons: list[Season], positions: list[str | None]) -> dict[str | None, dict[str, float]]:
    """Prior per position (G, F, C; a multi-position player counts in each) and for None = all.
    Pool: player seasons with at least MIN_MINUTES."""
    groups: dict[str | None, list[Season]] = defaultdict(list)
    for s, pos in zip(seasons, positions):
        if s.min < MIN_MINUTES:
            continue
        groups[None].append(s)
        for p in (pos or "").split(","):
            if p:
                groups[p].append(s)
    return {g: pool_prior(rows) for g, rows in groups.items()}


def prior_for(priors: dict, position: str | None) -> dict[str, float]:
    keys = [p for p in (position or "").split(",") if p in priors]
    if not keys:
        return priors[None]
    return {c: sum(priors[k][c] for k in keys) / len(keys) for c in COMPONENTS}


def history_before(seasons: dict[str, Season], target: str, n: int) -> list[Season]:
    """The n seasons before `target`, newest first."""
    return [seasons[s] for s in sorted((s for s in seasons if s < target), reverse=True)[:n]]


def cases(data: History, positions: dict, targets: list[str], n: int = 3):
    """(target Season, history newest first, prior) for every player with a target row above
    MIN_MINUTES and at least one past season. The prior uses only seasons before the target."""
    out = []
    for t in targets:
        past = [(s, positions.get(p)) for p, ss in data.items() for k, s in ss.items() if k < t]
        priors = priors_by_position([s for s, _ in past], [pos for _, pos in past])
        for p, ss in data.items():
            if t not in ss or ss[t].min < MIN_MINUTES:
                continue
            hist = history_before(ss, t, n)
            if hist:
                out.append((ss[t], hist, prior_for(priors, positions.get(p)), p))
    return out


def rate_error(case_list, c: str, p: Params) -> float:
    """Minutes-weighted (attempt-weighted for percentages) squared error of component c."""
    err = wsum = 0.0
    for target, hist, prior, _ in case_list:
        n, d = rate_parts(target, c)
        if d <= 0:
            continue
        pred = rates(hist, prior, p)[c]
        err += d * (n / d - pred) ** 2
        wsum += d
    return err / wsum if wsum else 0.0


def fit_k(case_list, p: Params) -> tuple[dict[str, float], dict[str, float]]:
    """Best K per component and its error."""
    best, errs = {}, {}
    for c in COMPONENTS:
        scores = {k: rate_error(case_list, c, replace(p, k={**p.k, c: float(k)})) for k in K_GRID}
        best[c] = float(min(scores, key=scores.get))
        errs[c] = scores[best[c]]
    return best, errs


def normalised_error(errs: dict[str, float], base: dict[str, float]) -> float:
    """Sum of component errors, each divided by a reference error (so no unit dominates)."""
    return sum(errs[c] / base[c] for c in COMPONENTS if base[c])


def fit_rates(case_list) -> tuple[Params, dict]:
    """Season weights and K. Returns the fitted Params and a report."""
    ref = None
    report = {}
    best = None
    for w in WEIGHT_GRID:
        p = Params(season_weights=tuple(float(x) for x in w))
        k, errs = fit_k(case_list, p)
        ref = ref or errs
        score = normalised_error(errs, ref)
        report[w] = {"score": score, "k": k, "errors": errs}
        if best is None or score < best[0]:
            best = (score, replace(p, k=k))
    return best[1], report


def fit_gp(data: History, targets: list[str], weights: tuple[float, ...], n: int = 3) -> tuple[float, float, float]:
    """Least squares: target share = a + b x weighted past share. Third value: the median
    residual of rotation players (20+ minutes per game in the newest past season), so that
    a + b x share + shift is the median season, not the mean."""
    xs, ys, rot = [], [], []
    for t in targets:
        for ss in data.values():
            if t not in ss:
                continue
            hist = history_before(ss, t, n)
            if not hist:
                continue
            ws = weights[: len(hist)]
            if not sum(ws):
                continue
            xs.append(sum(w * min(s.gp / SEASON_GAMES, 1.0) for w, s in zip(ws, hist)) / sum(ws))
            ys.append(min(ss[t].gp / SEASON_GAMES, 1.0))
            rot.append(hist[0].gp > 0 and hist[0].min / hist[0].gp >= 20)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    res = sorted(y - (a + b * x) for x, y, r in zip(xs, ys, rot) if r)
    return a, b, res[len(res) // 2]


def fit_age(data: History) -> dict[str, dict[int, float]]:
    """Change factor of each rate from age a-1 to a, per age bucket (ratio of pooled rates over
    pairs of consecutive seasons, both above MIN_MINUTES). Buckets with fewer than 15 pairs = 1.0."""
    pairs = defaultdict(list)  # bucket -> [(prev Season, next Season)]
    for ss in data.values():
        keys = sorted(ss)
        for a, b in zip(keys, keys[1:]):
            s0, s1 = ss[a], ss[b]
            if s1.age is None or s0.min < MIN_MINUTES or s1.min < MIN_MINUTES:
                continue
            if int(b[:4]) - int(a[:4]) != 1:
                continue
            for lo, hi in AGE_BUCKETS:
                if lo <= s1.age <= hi:
                    pairs[(lo, hi)].append((s0, s1))
    out: dict[str, dict[int, float]] = {c: {} for c in COMPONENTS}
    for (lo, hi), ps in pairs.items():
        for c in COMPONENTS:
            if len(ps) < 15:
                f = 1.0
            else:
                # Harmonic-mean weights: a pair counts by the smaller sample of its two seasons.
                num = den = 0.0
                for s0, s1 in ps:
                    n0, d0 = rate_parts(s0, c)
                    n1, d1 = rate_parts(s1, c)
                    if d0 <= 0 or d1 <= 0 or n0 <= 0:
                        continue
                    w = 2 * d0 * d1 / (d0 + d1)
                    num += w * (n1 / d1)
                    den += w * (n0 / d0)
                f = num / den if den else 1.0
            for age in range(lo, hi + 1):
                out[c][age] = f
    return out


__all__ = ["MIN_MINUTES", "PER_ATT", "cases", "fit_age", "fit_gp", "fit_rates", "prior_for", "priors_by_position"]
