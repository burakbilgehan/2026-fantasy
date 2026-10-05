"""Room price and opportunity (T-025 dollar part, docs/modules/pricing.md). Pure functions, no DB.

Two numbers per player next to our model value:
- expected room price: what this room will pay for him. Market signals (Yahoo average cost,
  ESPN average cost, Fantrax ADP) give a market order; the room's price-by-rank curve turns his
  place in that order into this room's dollars. So the room's own shape (our league pays 49% of
  the budget for the top 24) replaces each site's shape, and the order comes from the market.
- room value: the room's price at his rank in OUR model. What he would cost if the room saw him
  the way we do.
opportunity = room value - expected room price. Positive: the room underrates him.

Everything takes plain inputs (a curve, prices, ranks), so the live draft board can pass a
curve adjusted for money and slots left during the draft (T-018).
"""

from collections.abc import Iterable, Mapping

# Weights of the market signals (user, 2026-10-05: Yahoo-weighted, our league plays on Yahoo).
MARKET_WEIGHTS = {"yahoo": 2.0, "espn": 1.0, "fantrax": 1.0}


def price_curve(prices: Iterable[float], length: int) -> list[float]:
    """Room price by rank (index 0 = rank 1), from one auction's prices, sorted high to low.
    Smoothed with a centered 5-wide mean (keeps the top two as sold), padded with 1 USD."""
    p = sorted((float(x) for x in prices), reverse=True)
    out = []
    for i in range(len(p)):
        if i < 2:
            out.append(p[i])
            continue
        lo, hi = max(0, i - 2), min(len(p), i + 3)
        out.append(sum(p[lo:hi]) / (hi - lo))
    # Never rising with rank.
    for i in range(1, len(out)):
        out[i] = min(out[i], out[i - 1])
    return (out + [1.0] * length)[:length]


def market_ranks(signals: Mapping[str, Mapping[object, float]], weights: Mapping[str, float] = MARKET_WEIGHTS,
                 adp_sources: Iterable[str] = ("fantrax",)) -> dict[object, float]:
    """Weighted mean market rank per player (1 = best), over the sources that list him.

    signals: {source: {player: number}}; dollar sources (higher = better) and ADP sources (lower =
    better) are both turned into a rank inside their own source. Plain ranks, not percentiles: the
    sources list different numbers of players, and a percentile would make a short list's steps
    bigger (found 2026-10-05: Yahoo's shorter list pushed Doncic above Wembanyama).
    """
    adp = set(adp_sources)
    parts: dict[object, list[tuple[float, float]]] = {}
    for src, vals in signals.items():
        w = weights.get(src, 0.0)
        if not w or not vals:
            continue
        order = sorted(vals, key=lambda k: vals[k], reverse=src not in adp)
        for i, k in enumerate(order):
            parts.setdefault(k, []).append((w, float(i + 1)))
    return {k: sum(w * r for w, r in v) / sum(w for w, _ in v) for k, v in parts.items()}


def market_order(signals: Mapping[str, Mapping[object, float]], weights: Mapping[str, float] = MARKET_WEIGHTS,
                 adp_sources: Iterable[str] = ("fantrax",)) -> list[object]:
    """Players ordered by the market, best first."""
    r = market_ranks(signals, weights, adp_sources)
    return sorted(r, key=r.get)


def curve_at(curve: list[float], rank: float) -> float:
    """Curve value at a fractional rank (linear between neighbours), 1 USD past the end."""
    if rank <= 1:
        return curve[0]
    i = int(rank) - 1
    if i + 1 >= len(curve):
        return curve[-1] if i < len(curve) else 1.0
    f = rank - int(rank)
    return curve[i] * (1 - f) + curve[i + 1] * f


def expected_prices(ranks: Mapping[object, float] | list[object], curve: list[float]) -> dict[object, float]:
    """Expected room price: the curve at the player's (fractional) market rank. Near ties get near
    prices: two players at mean ranks 2.5 and 3.0 are not 7 USD apart only because one is listed first.
    A list (an order) is read as ranks 1, 2, 3, ..."""
    if isinstance(ranks, list):
        ranks = {k: float(i + 1) for i, k in enumerate(ranks)}
    return {k: curve_at(curve, r) for k, r in ranks.items()}


def room_values(model_rank: Mapping[object, int], curve: list[float]) -> dict[object, float]:
    """Room price at the player's rank in our model (rank 1 = best)."""
    return {k: (curve[r - 1] if 0 < r <= len(curve) else 1.0) for k, r in model_rank.items()}


def opportunity(room_value: Mapping[object, float], expected: Mapping[object, float]) -> dict[object, float]:
    return {k: room_value[k] - expected.get(k, 1.0) for k in room_value}
