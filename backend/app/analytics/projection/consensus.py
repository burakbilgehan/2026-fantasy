"""Consensus base (T-025, base v2). Pure functions, no DB.

The base is a weighted average of the season projections we trust (user, 2026-10-05):
Yahoo 2, FanScout 1 (added 2026-10-05), Fantrax 1, ESPN 1, FantasyPros 1, our own stat model 1 (Fantrax lowered from 2 on
2026-10-05: in the top 200 it misses the other sources 3 to 4 times as often; it looks stale for
last season's breakouts). Each source covers what it
covers: a component is averaged over the sources that have it, with their weights. FantasyPros
has no shot attempts (only FG% and FT%); Yahoo has no minutes.
Averages are per game. The result becomes per-minute rates at the consensus minutes, so the
engine keeps PTS = 2 FGM + FTM + 3PM and the context layer can scale the rates.
"""

from app.analytics.projection.engine import COMPONENTS, PER_MIN

WEIGHTS = {"yahoo": 2.0, "fanscout": 1.0, "fantrax": 1.0, "espn": 1.0, "fantasypros": 1.0, "own-stat": 1.0}
MINUTE_WEIGHTS = {"fanscout": 1.0, "fantrax": 1.0, "espn": 1.0, "fantasypros": 1.0}  # Yahoo publishes no minutes


def per_game(totals: dict[str, float]) -> dict[str, float]:
    """Per game components from season totals (keys from STAT_FIELDS, optional `min`)."""
    gp = totals.get("gp") or 0.0
    if gp <= 0:
        return {}
    out = {c: totals[c] / gp for c in PER_MIN if totals.get(c) is not None}
    if totals.get("fga"):
        out["fg_pct"] = totals["fgm"] / totals["fga"]
    if totals.get("fta"):
        out["ft_pct"] = totals["ftm"] / totals["fta"]
    if totals.get("min"):
        out["mpg"] = totals["min"] / gp
    return out


def combine(lines: dict[str, dict[str, float]], weights: dict[str, float] = WEIGHTS) -> dict[str, float]:
    """Weighted mean per component over the sources that have it. Percentages are weighted by
    source weight only (each source's attempts are already in its own FGA/FTA)."""
    out = {}
    for c in COMPONENTS:
        num = den = 0.0
        for src, pg in lines.items():
            if c in pg and pg[c] is not None:
                w = weights.get(src, 0.0)
                num += w * pg[c]
                den += w
        if den:
            out[c] = num / den
    return out


def consensus_minutes(lines: dict[str, dict[str, float]]) -> float | None:
    num = den = 0.0
    for src, w in MINUTE_WEIGHTS.items():
        m = lines.get(src, {}).get("mpg")
        if m:
            num += w * m
            den += w
    return num / den if den else None


def to_rates(pg: dict[str, float], mpg: float, fallback: dict[str, float]) -> dict[str, float]:
    """Engine rates from a per-game line at `mpg` minutes. Missing components come from `fallback`."""
    out = {}
    for c in COMPONENTS:
        if c not in pg:
            out[c] = fallback[c]
        elif c in PER_MIN:
            out[c] = pg[c] / mpg if mpg else fallback[c]
        else:
            out[c] = pg[c]
    return out
