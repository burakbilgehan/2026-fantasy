"""Backtest helpers for T-017 (pure): auction knapsack and weekly H2H category scoring.

Team stats in a week = sum of the box scores of every rostered player's games that week.
Draft and hold: no lineup cap, no waivers, no trades, positions ignored. The same rules
apply to every team.
"""

from collections.abc import Iterable

STAT_KEYS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
CATS = ("fg_pct", "ft_pct", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def best_roster(
    candidates: dict[object, tuple[float, int]], slots: int = 12, budget: int = 200,
) -> list[object]:
    """Exactly `slots` players, sum of prices <= budget, max sum of objective.

    candidates: player -> (objective, price). Prices are whole dollars >= 1.
    """
    items = [(p, obj, max(1, int(price))) for p, (obj, price) in candidates.items() if price <= budget]
    neg = float("-inf")
    # dp[k][b] = best objective with k players costing exactly b
    dp = [[neg] * (budget + 1) for _ in range(slots + 1)]
    dp[0][0] = 0.0
    take: list[list[bytearray]] = []
    for _, obj, price in items:
        rows = []
        for k in range(slots, 0, -1):
            prev, cur = dp[k - 1], dp[k]
            flags = bytearray(budget + 1)
            for b in range(budget, price - 1, -1):
                v = prev[b - price]
                if v != neg and v + obj > cur[b]:
                    cur[b] = v + obj
                    flags[b] = 1
            rows.append(flags)
        take.append(rows[::-1])  # index k-1
    b = max(range(budget + 1), key=lambda x: dp[slots][x])
    if dp[slots][b] == neg:
        raise ValueError("no roster fits the budget")
    picked, k = [], slots
    for i in range(len(items) - 1, -1, -1):
        if k and take[i][k - 1][b]:
            picked.append(items[i][0])
            b -= items[i][2]
            k -= 1
    return picked


def team_weeks(
    roster: Iterable[object], player_weeks: dict[object, dict[object, dict[str, float]]], weeks: list[object],
) -> dict[object, dict[str, float]]:
    """Week -> summed stats of the roster."""
    out = {w: dict.fromkeys(STAT_KEYS, 0.0) for w in weeks}
    for p in roster:
        for w, s in player_weeks.get(p, {}).items():
            if w in out:
                acc = out[w]
                for k in STAT_KEYS:
                    acc[k] += s[k]
    return out


def _cat(s: dict[str, float], c: str) -> float:
    if c == "fg_pct":
        return s["fgm"] / s["fga"] if s["fga"] else 0.0
    if c == "ft_pct":
        return s["ftm"] / s["fta"] if s["fta"] else 0.0
    return s[c]


def matchup(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    """(categories won by a, ties count 0.5; matchup result for a: 1, 0.5 or 0)."""
    won = lost = 0.0
    for c in CATS:
        x, y = _cat(a, c), _cat(b, c)
        if c == "tov":
            x, y = -x, -y
        if x > y:
            won += 1
        elif x < y:
            lost += 1
    cats = won + (len(CATS) - won - lost) / 2
    return cats, 1.0 if won > lost else 0.5 if won == lost else 0.0


def all_play(
    team: dict[object, dict[str, float]], opponents: list[dict[object, dict[str, float]]], weeks: list[object],
) -> tuple[float, float]:
    """(category win share, matchup win share) of `team` against every opponent in every week."""
    cats = games = 0.0
    n = 0
    for opp in opponents:
        for w in weeks:
            c, g = matchup(team[w], opp[w])
            cats += c
            games += g
            n += 1
    return cats / (n * len(CATS)), games / n
