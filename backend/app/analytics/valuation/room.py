"""Static and dynamic prices (T-025 dollar part, docs/modules/pricing.md). Pure functions, no DB.

Names (user, 2026-10-05):
- static price: our model's dollars (the model and dollar method picked in the value table). OURS.
- dynamic worth: what a player is worth to us at this point of the draft. At the start of a
  draft it equals the static price. OURS.
- dynamic market price: what the room is expected to pay. At the start of a draft it equals the
  market price below (the others' view). During a draft it moves away from it with the room's
  spending (T-018, T-013): if the top players went for more than their market price, the next
  top players get dearer too.
- opportunity = dynamic worth - dynamic market price.

Market price = weighted mean of the market's own dollars, over the sources that price the player:
Yahoo average cost x2, ESPN average cost x1, Fantrax x1. Fantrax has no prices, only ADP: its ADP
order is put on Yahoo's dollar scale (the Fantrax player at ADP place i gets the Yahoo average cost
of the Yahoo player at ADP place i). No rank curve, no last-season auction as a rule.
"""

from collections.abc import Mapping

MARKET_WEIGHTS = {"yahoo": 2.0, "espn": 1.0, "fantrax": 1.0}


def adp_to_dollars(adp: Mapping[object, float], ref_adp: Mapping[object, float],
                   ref_cost: Mapping[object, float]) -> dict[object, float]:
    """Dollars for an ADP-only source: its ADP order on the reference source's dollar scale.

    ref_*: a source with both ADP and average cost (Yahoo). Its costs, in its own ADP order and made
    never-rising, form the scale; the i-th player by `adp` gets the scale's i-th value (1 USD past it).
    """
    ref = [k for k in sorted(ref_adp, key=ref_adp.get) if ref_cost.get(k)]
    scale = [float(ref_cost[k]) for k in ref]
    for i in range(1, len(scale)):
        scale[i] = min(scale[i], scale[i - 1])
    order = sorted(adp, key=adp.get)
    return {k: (scale[i] if i < len(scale) else 1.0) for i, k in enumerate(order)}


def market_prices(dollars: Mapping[str, Mapping[object, float]],
                  weights: Mapping[str, float] = MARKET_WEIGHTS) -> dict[object, float]:
    """Weighted mean price per player over the sources that price him (values below 1 count as 1)."""
    parts: dict[object, list[tuple[float, float]]] = {}
    for src, vals in dollars.items():
        w = weights.get(src, 0.0)
        if not w:
            continue
        for k, v in vals.items():
            parts.setdefault(k, []).append((w, max(float(v), 1.0)))
    return {k: sum(w * x for w, x in v) / sum(w for w, _ in v) for k, v in parts.items()}


def opportunity(worth: Mapping[object, float], market: Mapping[object, float]) -> dict[object, float]:
    """Dynamic worth minus dynamic market price; a player with no market price counts at 1 USD."""
    return {k: worth[k] - market.get(k, 1.0) for k in worth}
