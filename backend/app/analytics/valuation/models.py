"""Model registry. A model turns a player's 9 category z values into one total.

Descriptions are the dropdown text (`docs/modules/valuation.md`). The frontend reads them from here.
Order = dropdown order: the default (G-score, user decision 2026-10-13) first.
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
    needs: tuple[str, ...] = ()  # extra inputs: "g_weights", "punt", "simulation"
    transform: str | None = None  # category transform before standardising (core.Settings.transform)
    simulation: bool = False  # totals come from app.analytics.valuation.simulate, not from `total`


# Josh Lloyd's published DURANT H2H weights (joshlloydfantasy.com/research/durant-fantasy-basketball,
# read 2026-10-13). Turnovers are excluded; Minus 1 removes the worst of these eight.
DURANT_H2H_WEIGHTS = {"fg_pct": 0.60, "ft_pct": 0.60, "tpm": 0.60, "pts": 1.00, "reb": 0.94, "ast": 0.75,
                      "stl": 0.60, "blk": 0.60}
DURANT_TOV_WEIGHT = 0.50  # the broad DURANT: every other category 1.00


def _zscore(z: dict[str, float], s: Settings) -> float:
    return sum(z[c] for c in CATEGORIES)


def _punt(z: dict[str, float], s: Settings) -> float:
    return sum(z[c] for c in CATEGORIES if c not in s.punt)


def _minus1(z: dict[str, float], s: Settings) -> float:
    vals = [z[c] for c in CATEGORIES]
    return sum(vals) - min(vals)


def _durant_h2h(z: dict[str, float], s: Settings) -> float:
    parts = [w * z[c] for c, w in DURANT_H2H_WEIGHTS.items()]
    return sum(parts) - min(parts)


def _durant_all(z: dict[str, float], s: Settings) -> float:
    return sum(z[c] for c in CATEGORIES if c != "tov") + DURANT_TOV_WEIGHT * z["tov"]


def _gscore(z: dict[str, float], s: Settings) -> float:
    if not s.g_weights:
        raise ValueError("G-score needs g_weights (from game logs)")
    return sum(s.g_weights[c] * z[c] for c in CATEGORIES)


MODELS: dict[str, Model] = {m.key: m for m in (
    Model("gscore", "G-score",
          "Classic, but noisy categories (steals, percentages, turnovers) weigh less, because "
          "weekly results in them are closer to luck. Best match to our weekly H2H simulation (2026-10-13 research).",
          _gscore, ("g_weights",)),
    Model("zscore", "Z-score 9-cat",
          "Classic. Each category: distance from the pool average in standard deviations. Sum of 9.",
          _zscore),
    Model("punt", "Punt z-score",
          "Classic, with the categories you turn off removed.",
          _punt, ("punt",)),
    Model("minus1", "Minus-1",
          "Classic, without each player's own worst category. The value for a team that punts that category.",
          _minus1),
    Model("durant", "DURANT H2H (Lloyd)",
          "Josh Lloyd's head-to-head list as he published it: skew-corrected categories (Yeo-Johnson), "
          "points weigh most (REB 0.94, AST 0.75, the rest 0.60), no turnovers, the player's worst category dropped. "
          "His list is per game with the pool set to all.",
          _durant_h2h, transform="yeo_johnson"),
    Model("durant_all", "DURANT (Lloyd, all categories)",
          "Lloyd's broad DURANT for roto and H2H: skew-corrected categories, all equal, turnovers at half weight. "
          "Per game, pool all.",
          _durant_all, transform="yeo_johnson"),
    Model("sim", "Simulated H2H",
          "Our own model: the player joins hundreds of random teams drawn from the top 144, every team plays "
          "every fantasy week on expected weekly lines (per game x games that week x availability). Value = "
          "category wins above 50% per 100 matchups. Totals basis counts games played; per game assumes every week played.",
          _zscore, ("simulation",), simulation=True),
)}
