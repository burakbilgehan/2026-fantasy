"""Category values for one base (pure, no DB).

A base row is one player's season totals with the STAT_FIELDS keys (gp, fgm, fga, ...).
The basis decides the unit: `totals` uses the totals as given (projected GP is in them),
`per_game` divides by gp.

FG% and FT% are volume-weighted impact: makes - pool_rate * attempts. A high-volume
shooter moves a team's percentage more than a low-volume one with the same rate.
TO counts negative (lower is better).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from statistics import fmean, pstdev

CATEGORIES = ("fg_pct", "ft_pct", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
COUNTING = ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")
PERCENT = {"fg_pct": ("fgm", "fga"), "ft_pct": ("ftm", "fta")}
BASES = ("totals", "per_game")


@dataclass(frozen=True)
class Settings:
    basis: str = "totals"
    pool: int | None = 200  # reference pool for mean and SD: top N by the model's own total; None = all rows
    punt: frozenset[str] = frozenset()  # categories the punt model leaves out
    g_weights: dict[str, float] = field(default_factory=dict)  # G-score: weight per category
    iterations: int = 3  # pool refinement rounds


def basis_stats(row: dict, basis: str) -> dict[str, float]:
    """The row's raw stats in the basis unit."""
    if basis == "totals":
        return dict(row)
    if basis == "per_game":
        gp = row["gp"]
        return {k: (v / gp if k != "gp" else 1.0) for k, v in row.items()}
    raise ValueError(f"unknown basis {basis}")


def category_z(
    stats: dict[object, dict[str, float]], pool: Iterable[object],
) -> dict[object, dict[str, float]]:
    """Z per category for every player. Mean, SD and shooting rates come from `pool`."""
    pool = list(pool)
    rates = {
        c: sum(stats[p][m] for p in pool) / (sum(stats[p][a] for p in pool) or 1.0)
        for c, (m, a) in PERCENT.items()
    }

    def raw(s: dict[str, float], c: str) -> float:
        if c in PERCENT:
            m, a = PERCENT[c]
            return s[m] - rates[c] * s[a]
        return s[c]

    moments = {}
    for c in CATEGORIES:
        xs = [raw(stats[p], c) for p in pool]
        moments[c] = (fmean(xs), pstdev(xs) or 1.0)
    out = {}
    for p, s in stats.items():
        z = {c: (raw(s, c) - moments[c][0]) / moments[c][1] for c in CATEGORIES}
        z["tov"] = -z["tov"]
        out[p] = z
    return out


def value(
    rows: dict[object, dict[str, float]],
    total: Callable[[dict[str, float], Settings], float],
    settings: Settings,
) -> tuple[dict[object, dict[str, float]], dict[object, float]]:
    """Category z and model total for every row with gp > 0.

    The pool starts as all rows. Each round takes the top N by the model's total and
    computes mean and SD again on them.
    """
    stats = {p: basis_stats(r, settings.basis) for p, r in rows.items() if r["gp"] > 0}
    pool = list(stats)
    for _ in range(max(1, settings.iterations)):
        z = category_z(stats, pool)
        totals = {p: total(zp, settings) for p, zp in z.items()}
        if settings.pool is None or settings.pool >= len(stats):
            break
        pool = sorted(totals, key=totals.get, reverse=True)[: settings.pool]
    return z, totals
