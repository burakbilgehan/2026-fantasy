"""Model total -> auction dollars (pure).

Plain: value over replacement. Replacement = the value of player n_drafted + 1. Every
drafted player gets 1 USD plus a share of (budget - n_drafted) in proportion to the value
over replacement. Players below the top n_drafted get 0.

SAVOR (streaming-adjusted value over replacement): cheap players are worth less because
waivers replace them during the season. Formula from the appendix of arXiv 2307.02188v4,
as documented in zer2.github.io/fantasy-basketball-optimizer (Auction mode):
    d * Phi(d / s) - s / sqrt(2 pi) * (1 - exp(-d^2 / (2 s^2)))
then rescaled so that the total stays the same. d = plain dollars above the 1 USD minimum.
"""

import math


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def savor(d: float, spread: float) -> float:
    if spread <= 0:
        return d
    return d * _phi(d / spread) - spread / math.sqrt(2 * math.pi) * (1 - math.exp(-d * d / (2 * spread * spread)))


def to_dollars(
    totals: dict[object, float],
    n_drafted: int = 144,
    budget: float = 2400.0,
    method: str = "plain",
    spread: float = 10.0,
) -> dict[object, float]:
    ranked = sorted(totals, key=totals.get, reverse=True)
    top = ranked[:n_drafted]
    replacement = totals[ranked[n_drafted]] if len(ranked) > n_drafted else min(totals.values())
    vor = {p: max(totals[p] - replacement, 0.0) for p in top}
    pool_money = budget - len(top)
    scale = pool_money / (sum(vor.values()) or 1.0)
    extra = {p: v * scale for p, v in vor.items()}
    if method == "savor":
        adjusted = {p: savor(d, spread) for p, d in extra.items()}
        k = sum(extra.values()) / (sum(adjusted.values()) or 1.0)
        extra = {p: d * k for p, d in adjusted.items()}
    elif method != "plain":
        raise ValueError(f"unknown dollar method {method}")
    out = {p: 0.0 for p in totals}
    out.update({p: 1.0 + d for p, d in extra.items()})
    return out
