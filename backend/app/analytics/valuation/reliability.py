"""Reliability score: share of games played in the last seasons (pure). A second number, not a value.

Seasons before the player's first season in the window do not count (rookie, not yet in
the league). A missing season after the first one counts as 0 games.
"""


def reliability(gp_by_season: dict[str, float | None], seasons: list[str], season_games: int = 82) -> float | None:
    """`seasons` in time order. None when the player has no season in the window."""
    shares = []
    started = False
    for s in seasons:
        gp = gp_by_season.get(s)
        if gp is None and not started:
            continue
        started = True
        shares.append(min((gp or 0) / season_games, 1.0))
    return sum(shares) / len(shares) if shares else None
