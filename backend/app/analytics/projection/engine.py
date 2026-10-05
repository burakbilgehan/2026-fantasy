"""Own projection, base layer (T-025). Pure functions, no DB.

projection = projected minutes x per-minute rates x projected GP.

Rates: past seasons, weighted by season weight x minutes, then pulled toward a prior
(the position average of the pool) by K "phantom" minutes or attempts. A noisy stat gets
a large K (strong pull), a stable stat a small K. K values come from `fit.py`.
FG% and FT% are rates per attempt. PTS is never projected on its own: PTS = 2 FGM + FTM + 3PM
(the identity holds for every stat line we checked, see DATA_SOURCES.md), so the line stays
consistent.

GP: a linear blend of the player's past share of games and the pool mean (fit.py), minus
known games out (injury) and late-season games out (shutdown).
"""

from dataclasses import dataclass, field

# Components with their numerator and denominator. Denominator "min" = per minute.
PER_MIN = ("fga", "fta", "tpm", "reb", "ast", "stl", "blk", "tov")
PER_ATT = {"fg_pct": ("fgm", "fga"), "ft_pct": ("ftm", "fta")}
COMPONENTS = PER_MIN + tuple(PER_ATT)
SEASON_GAMES = 82


@dataclass(frozen=True)
class Params:
    # Weight of the last, second to last and third to last season (assumed 5/3/2).
    season_weights: tuple[float, ...] = (5.0, 3.0, 2.0)
    # K per component: phantom minutes (per-minute stats) or attempts (percentages) at the prior rate.
    k: dict[str, float] = field(default_factory=lambda: {c: 300.0 for c in PER_MIN} | {"fg_pct": 300.0, "ft_pct": 150.0})
    # GP share = gp_a + gp_b x weighted past share (fit.py).
    gp_a: float = 0.45
    gp_b: float = 0.40
    # Added to the GP share so the projection is the median outcome, not the mean (fit.py).
    # The mean is pulled down by a few season-long injuries; the user wants the typical season.
    gp_shift: float = 0.0
    # Age factor per component: {age: factor}; missing age or component = 1.0.
    age: dict[str, dict[int, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Season:
    """One past season, totals. `min` must be known."""

    season: str
    gp: float
    min: float
    stats: dict[str, float]  # fgm, fga, ftm, fta, tpm, reb, ast, stl, blk, tov
    age: int | None = None


def rate_parts(s: Season, c: str) -> tuple[float, float]:
    """(numerator, denominator) of component c in season s."""
    if c in PER_ATT:
        m, a = PER_ATT[c]
        return s.stats[m], s.stats[a]
    return s.stats[c], s.min


def rates(history: list[Season], prior: dict[str, float], p: Params) -> dict[str, float]:
    """Regressed rate per component. `history` newest first. Empty history = the prior."""
    out = {}
    for c in COMPONENTS:
        num = den = 0.0
        for w, s in zip(p.season_weights, history):
            n, d = rate_parts(s, c)
            num += w * n
            den += w * d
        # The newest season counts at full weight, older ones at a fraction, so K keeps one unit.
        scale = max(p.season_weights[: len(history)], default=1.0) or 1.0
        num, den = num / scale, den / scale
        out[c] = (num + p.k[c] * prior[c]) / (den + p.k[c]) if den + p.k[c] > 0 else prior[c]
    return out


def age_factor(c: str, age: int | None, p: Params) -> float:
    if age is None or c not in p.age:
        return 1.0
    curve = p.age[c]
    if age in curve:
        return curve[age]
    near = min(curve, key=lambda a: abs(a - age))  # outside the fitted range: nearest age
    return curve[near]


def project_gp(history: list[Season], p: Params, games_out: float = 0.0, late_games_out: float = 0.0) -> float:
    """Projected games played. Past share is weighted like the rates (seasons with 0 GP count)."""
    if history:
        ws = p.season_weights[: len(history)]
        share = sum(w * min(s.gp / SEASON_GAMES, 1.0) for w, s in zip(ws, history)) / sum(ws)
    else:
        share = (1.0 - p.gp_a) / p.gp_b if p.gp_b else 0.7  # no history: the pool mean share
        share = min(share, 1.0)
    gp = SEASON_GAMES * min(p.gp_a + p.gp_b * share + p.gp_shift, 1.0)
    return max(gp - games_out - late_games_out, 0.0)


def project(
    rate: dict[str, float], mpg: float, gp: float, age: int | None = None, p: Params | None = None,
    multipliers: dict[str, float] | None = None,
) -> dict[str, float]:
    """Season totals in the STAT_FIELDS shape, plus `min`.

    `multipliers` scale a component after aging (manual or expert adjustment, 1.0 = none).
    """
    p = p or Params()
    multipliers = multipliers or {}
    r = {c: rate[c] * age_factor(c, age, p) * multipliers.get(c, 1.0) for c in COMPONENTS}
    minutes = mpg * gp
    fga, fta = r["fga"] * minutes, r["fta"] * minutes
    fgm, ftm = min(r["fg_pct"], 1.0) * fga, min(r["ft_pct"], 1.0) * fta
    tpm = min(r["tpm"] * minutes, fgm)
    line = {
        "gp": gp, "min": minutes, "fgm": fgm, "fga": fga, "ftm": ftm, "fta": fta, "tpm": tpm,
        "pts": 2 * fgm + ftm + tpm,
    }
    for c in ("reb", "ast", "stl", "blk", "tov"):
        line[c] = r[c] * minutes
    return line
