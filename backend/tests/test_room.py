from app.analytics.valuation import room


def test_adp_to_dollars_uses_yahoo_scale():
    ref_adp = {"a": 1.5, "b": 3.0, "c": 10.0}
    ref_cost = {"a": 70.0, "b": 60.0, "c": 30.0}
    got = room.adp_to_dollars({"x": 2.0, "y": 1.1, "z": 40.0, "w": 90.0}, ref_adp, ref_cost)
    assert got == {"y": 70.0, "x": 60.0, "z": 30.0, "w": 1.0}


def test_market_price_weighted_mean_over_sources():
    m = room.market_prices({"yahoo": {"a": 70.0}, "espn": {"a": 82.0, "b": 0.4}, "fantrax": {"a": 61.0}})
    assert m["a"] == (2 * 70 + 82 + 61) / 4
    assert m["b"] == 1.0  # below 1 counts as 1


def test_opportunity():
    assert room.opportunity({"a": 66.0, "b": 10.0}, {"a": 49.0}) == {"a": 17.0, "b": 9.0}
