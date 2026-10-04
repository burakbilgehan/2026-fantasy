"""Model registry. A model turns a player's 9 category z values into one total.

Descriptions are the dropdown text (first draft, `docs/modules/valuation.md`). The
frontend reads them from here.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.analytics.valuation.core import CATEGORIES, Settings


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    description: str
    total: Callable[[dict[str, float], Settings], float]
    needs: tuple[str, ...] = ()  # extra inputs: "g_weights", "punt"


def _zscore(z: dict[str, float], s: Settings) -> float:
    return sum(z[c] for c in CATEGORIES)


def _punt(z: dict[str, float], s: Settings) -> float:
    return sum(z[c] for c in CATEGORIES if c not in s.punt)


def _minus1(z: dict[str, float], s: Settings) -> float:
    vals = [z[c] for c in CATEGORIES]
    return sum(vals) - min(vals)


def _durant(z: dict[str, float], s: Settings) -> float:
    vals = [z[c] for c in CATEGORIES if c != "tov"]
    return sum(vals) - min(vals)


def _gscore(z: dict[str, float], s: Settings) -> float:
    if not s.g_weights:
        raise ValueError("G-score needs g_weights (from game logs)")
    return sum(s.g_weights[c] * z[c] for c in CATEGORIES)


MODELS: dict[str, Model] = {m.key: m for m in (
    Model("zscore", "Z-score 9-cat",
          "Classic. Each category: distance from the pool average in standard deviations. Sum of 9.",
          _zscore),
    Model("punt", "Punt z-score",
          "Classic, with the categories you turn off removed.",
          _punt, ("punt",)),
    Model("minus1", "Minus-1",
          "Classic, without each player's own worst category.",
          _minus1),
    Model("durant", "DURANT approximation",
          "Minus-1 without turnovers. Our guess at Josh Lloyd's H2H ranking.",
          _durant),
    Model("gscore", "G-score",
          "Classic, but noisy categories (steals, percentages, turnovers) weigh less, because "
          "weekly results in them are closer to luck.",
          _gscore, ("g_weights",)),
)}
