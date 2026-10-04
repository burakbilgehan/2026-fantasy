"""Player valuation (T-017, T-010). Pure functions; no DB access. Spec: docs/modules/valuation.md."""

from app.analytics.valuation.core import BASES, CATEGORIES, Settings, value
from app.analytics.valuation.dollars import to_dollars
from app.analytics.valuation.gscore import g_weights
from app.analytics.valuation.models import MODELS, Model
from app.analytics.valuation.reliability import reliability


def run(rows: dict, model: str, settings: Settings, n_drafted: int = 144, budget: float = 2400.0,
        dollars: str = "plain", spread: float = 10.0) -> dict[object, dict]:
    """Per player: category z, total, rank, dollars."""
    z, totals = value(rows, MODELS[model].total, settings)
    usd = to_dollars(totals, n_drafted, budget, dollars, spread)
    ranked = sorted(totals, key=totals.get, reverse=True)
    return {p: {"z": z[p], "total": totals[p], "rank": i + 1, "dollars": usd[p]} for i, p in enumerate(ranked)}


__all__ = ["BASES", "CATEGORIES", "MODELS", "Model", "Settings", "g_weights", "reliability", "run", "to_dollars", "value"]
