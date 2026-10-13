"""Player valuation (T-017, T-010). Pure functions; no DB access. Spec: docs/modules/valuation.md."""

from dataclasses import replace

from app.analytics.valuation.core import BASES, CATEGORIES, Settings, value
from app.analytics.valuation.dollars import to_dollars
from app.analytics.valuation.gscore import g_weights
from app.analytics.valuation.models import MODELS, Model
from app.analytics.valuation.reliability import reliability


def run(rows: dict, model: str, settings: Settings, n_drafted: int = 144, budget: float = 2400.0,
        dollars: str = "plain", spread: float = 10.0) -> dict[object, dict]:
    """Per player: category z, total, rank, dollars.

    A model with a transform (DURANT) sets it on the settings. The simulated model takes its totals
    from `simulate` (settings.sim must hold its inputs); its z are the plain z for display.
    """
    m = MODELS[model]
    if m.transform and settings.transform != m.transform:
        settings = replace(settings, transform=m.transform)
    z, totals = value(rows, m.total, settings)
    if m.simulation:
        if settings.sim is None:
            raise ValueError("the simulated model needs settings.sim (SimInputs)")
        from app.analytics.valuation.simulate import simulate

        totals = simulate(rows, settings, settings.sim, pool_size=n_drafted)
    usd = to_dollars(totals, n_drafted, budget, dollars, spread)
    ranked = sorted(totals, key=totals.get, reverse=True)
    return {p: {"z": z[p], "total": totals[p], "rank": i + 1, "dollars": usd[p]} for i, p in enumerate(ranked)}


__all__ = ["BASES", "CATEGORIES", "MODELS", "Model", "Settings", "g_weights", "reliability", "run", "to_dollars", "value"]
