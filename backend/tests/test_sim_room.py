"""Sim room (app/api/sim.py, app/analytics/draftsim.py): budget cap, spend-down, strong room makeup."""

import numpy as np
import pytest

from app.analytics.draftsim import Manager, auction, bid_cap, spend_factor
from app.api import sim


def test_bid_cap_reserve_one_is_the_old_rule():
    for money, slots in ((200, 12), (37, 5), (3, 3), (1, 1)):
        assert bid_cap(money, slots, 1.0) == money - (slots - 1)


def test_bid_cap_keeps_the_reserve_per_other_slot():
    assert bid_cap(200, 12, 10.0) == 200 - 11 * 10
    assert bid_cap(200, 12, 12.5) == 62  # floor of 62.5


def test_bid_cap_broken_plan_falls_back_to_even_split():
    # 20 USD for 4 slots with a 10 USD reserve: the reserve drops to 5, so he can still bid 5.
    assert bid_cap(20, 4, 10.0) == 5
    # Never below the hard rule of 1 USD per other open slot.
    assert bid_cap(4, 4, 10.0) == 1
    assert bid_cap(50, 0, 10.0) == 0


def test_auction_respects_the_reserve():
    rng = np.random.default_rng(0)
    a = Manager("A", "x", {1: 190.0, 2: 5.0, 3: 5.0}, noise=0.0, money=200, slots=3, reserve=10.0)
    b = Manager("B", "y", {1: 185.0, 2: 4.0, 3: 4.0}, noise=0.0, money=200, slots=3)
    log = auction([a, b], [1, 2, 3], rng)
    first = log[0]
    # A values him more but may bid only 200 - 2 x 10 = 180; B wins at 181.
    assert first["player"] == 1 and first["winner"] == "B" and first["price"] == 181


def test_spend_factor():
    best = np.array([10.0, 5.0, 3.0])
    assert spend_factor(10, 2, best) == 1.0  # money below what the best two are worth to him
    assert spend_factor(20, 2, best) == pytest.approx(20 / 15)
    assert spend_factor(500, 2, best) == 3.0  # capped
    assert spend_factor(10, 2, np.array([0.0, -1.0])) == 3.0  # nothing he wants left


def test_anchored_values_spend_the_budget():
    model = {p: float(100 - 3 * p) for p in range(40)}
    market = {p: float(max(1, 90 - 5 * p)) for p in range(20)}  # few players above 1 USD, as on Yahoo
    vals = sim.anchored_values(model, market, n_drafted=24, budget=1000.0)
    top = sorted(vals.values(), reverse=True)[:24]
    assert sum(top) == pytest.approx(1000.0)
    assert sorted(vals, key=vals.get, reverse=True)[:24] == sorted(
        model, key=lambda p: 0.5 * model[p] + 0.5 * market.get(p, 1.0), reverse=True)[:24]  # order kept
    low = {p: 0.5 for p in range(5)}
    assert sim.anchored_values(low, {}, 3, 10.0) == {p: 0.75 for p in range(5)}  # below 1 USD: not scaled


def _inp() -> dict:
    rng = np.random.default_rng(1)
    players = list(range(1, 201))
    base = {p: float(max(0.0, 60 - 0.4 * p)) for p in players}
    inp = {"n_drafted": 144, "budget": 2400.0, "teams": 12, "slots": 12, "base": {}, "season": "2026-27",
           "basis": "totals", "market": {p: max(1.0, v * 1.1) for p, v in base.items() if p <= 120}}
    for k in ("gscore", "zscore", "durant", "minus1", "points"):
        inp[k] = {p: max(0.0, v * float(rng.uniform(0.8, 1.2))) for p, v in base.items()}
    inp["g"] = inp["gscore"]
    return inp


def test_strong_room_has_only_strong_models_and_real_budget_shapes():
    models = [m for _, m, _ in sim.STRONG_ROOM]
    shapes = [s for _, _, s in sim.STRONG_ROOM]
    assert len(sim.STRONG_ROOM) == 11
    assert set(models) == {"gscore", "zscore", "durant"}
    assert (models.count("gscore"), models.count("zscore"), models.count("durant")) == (5, 3, 3)
    assert set(shapes) == set(sim.SHAPES)
    inp = _inp()
    ms = sim._managers("strong", "balanced", inp)
    assert len(ms) == 12 and ms[-1].mine
    styles = " ".join(m.style for m in ms)
    for weak in ("points", "bargain", "market", "stars first"):
        assert weak not in styles
    assert {m.noise for m in ms} == {sim.NOISE}  # me included
    per_slot = 2400 / 12 / 12
    for (_, _, shape), m in zip(sim.STRONG_ROOM, ms):
        share, stars = sim.SHAPES[shape]
        assert m.spend_down and m.reserve == pytest.approx(share * per_slot) and m.max_stars == stars
        assert sum(sorted(m.plain_values.values(), reverse=True)[:144]) == pytest.approx(2400.0)
        assert len(m.stars) == (sim.STAR_POOL if stars else 0)


def test_legacy_room_is_unchanged():
    ms = sim._managers("legacy", "balanced", _inp())
    assert [m.name for m in ms[:-1]] == [n for n, _ in sim.LEGACY_ROOM]
    assert ms[-1].noise == 0.05 and all(m.reserve == 1.0 and not m.spend_down for m in ms)


def test_plan_provider_hook():
    calls = []

    def provider(plan, base, season, basis):
        calls.append((plan, season, basis))
        return {1: 50.0, 2: 3.0}

    sim.register_plan("test_plan", "Test plan", provider)
    try:
        vals, stars, max_stars, _ = sim._plan_values("test_plan", {1: 10.0}, {}, {}, "2026-27", "totals")
        assert vals == {1: 50.0, 2: 3.0} and stars == set() and max_stars == 0
        assert calls == [("test_plan", "2026-27", "totals")]
        assert sim.plan_values_hook("balanced", {}, "2026-27", "totals") is None
        sim._check("projection", "strong", ["test_plan", "balanced"])
    finally:
        sim.PLANS.pop("test_plan", None)
        sim.PLAN_PROVIDERS.pop("test_plan", None)


def test_check_rejects_unknown_room_and_plan():
    with pytest.raises(sim.HTTPException):
        sim._check("projection", "weak", ["balanced"])
    with pytest.raises(sim.HTTPException):
        sim._check("projection", "strong", ["nope"])
