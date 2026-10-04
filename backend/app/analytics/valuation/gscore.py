"""G-score category weights from game logs (pure).

arXiv 2307.02188v5: G = (mu(q) - mu) / sqrt(sigma^2 + kappa * tau^2), kappa = 2N / (2N - 1).
sigma = SD of the players' mean weekly values over the pool, tau = a player's week-to-week
SD (pooled over the pool). Z-score is the case tau = 0. Here G = w_c * z_c with
w_c = sigma_c / sqrt(sigma_c^2 + kappa * tau_c^2), so the model can run on any basis.

Weeks are Monday to Sunday of the game date (assumed: Yahoo week 1 and the All-Star week
can differ). Percentages use weekly volume-weighted impact: makes - pool_rate * attempts.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from statistics import fmean, pstdev, pvariance

from app.analytics.valuation.core import CATEGORIES, PERCENT

LOG_FIELDS = ("min", "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def weekly_sums(logs: Iterable[dict]) -> dict[tuple, dict[tuple, dict[str, float]]]:
    """(player, season) -> (iso year, iso week) -> summed box score fields.

    A log is a dict with player, season, game_date and LOG_FIELDS.
    """
    out: dict[tuple, dict[tuple, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(LOG_FIELDS, 0.0)))
    for g in logs:
        week = g["game_date"].isocalendar()[:2]
        acc = out[(g["player"], g["season"])][week]
        for f in LOG_FIELDS:
            acc[f] += g[f]
    return out


def g_weights(logs: Iterable[dict], pool_size: int = 144, min_weeks: int = 4) -> dict[str, float]:
    """Weight per category. Each season is measured on its own, then sigma^2 and tau^2 are averaged.

    Pool per season: the `pool_size` players with the most minutes and at least `min_weeks` weeks.
    """
    weekly = weekly_sums(logs)
    by_season: dict[str, list[tuple]] = defaultdict(list)
    for key, weeks in weekly.items():
        if len(weeks) >= min_weeks:
            by_season[key[1]].append(key)
    sig2: dict[str, list[float]] = defaultdict(list)
    tau2: dict[str, list[float]] = defaultdict(list)
    n_pool = pool_size
    for season, keys in by_season.items():
        pool = sorted(keys, key=lambda k: sum(w["min"] for w in weekly[k].values()), reverse=True)[:pool_size]
        n_pool = len(pool)
        rates = {
            c: sum(w[m] for k in pool for w in weekly[k].values())
            / (sum(w[a] for k in pool for w in weekly[k].values()) or 1.0)
            for c, (m, a) in PERCENT.items()
        }
        for c in CATEGORIES:
            means, variances = [], []
            for k in pool:
                if c in PERCENT:
                    m, a = PERCENT[c]
                    xs = [w[m] - rates[c] * w[a] for w in weekly[k].values()]
                else:
                    xs = [w[c] for w in weekly[k].values()]
                means.append(fmean(xs))
                variances.append(pvariance(xs))
            sig2[c].append(pstdev(means) ** 2)
            tau2[c].append(fmean(variances))
    kappa = 2 * n_pool / (2 * n_pool - 1)
    out = {}
    for c in CATEGORIES:
        s2, t2 = fmean(sig2[c]), fmean(tau2[c])
        out[c] = math.sqrt(s2 / (s2 + kappa * t2)) if s2 + t2 > 0 else 1.0
    return out
