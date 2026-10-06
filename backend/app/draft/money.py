"""Money facts of a live draft room (T-018). Pure, no I/O.

The dynamic price logic (room price, temperature) was shelved by the user on 2026-10-06:
the table keeps the market price and our static price as references, nothing moves.
"""

from collections.abc import Mapping


def max_bids(money_left: Mapping[int, int], open_slots: Mapping[int, int]) -> dict[int, int]:
    """Highest bid a team can make: its money minus 1 USD per other open slot. 0 with no slot left."""
    return {t: (money_left[t] - (open_slots[t] - 1) if open_slots.get(t, 0) > 0 else 0) for t in money_left}
