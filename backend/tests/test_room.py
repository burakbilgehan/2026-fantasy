from app.analytics.valuation import room


def test_curve_sorted_padded_never_rising():
    c = room.price_curve([1, 50, 87, 10, 85, 30, 1], 10)
    assert c[0] == 87 and c[1] == 85 and len(c) == 10 and c[-1] == 1.0
    assert all(a >= b for a, b in zip(c, c[1:]))


def test_market_order_mixes_dollars_and_adp():
    signals = {"yahoo": {"a": 60, "b": 30, "c": 5}, "espn": {"a": 55, "b": 40}, "fantrax": {"a": 2.0, "b": 9.0, "c": 150.0}}
    assert room.market_order(signals) == ["a", "b", "c"]
    # ADP: lower is better; a player only in Fantrax still gets a place.
    assert room.market_order({"fantrax": {"x": 50.0, "y": 3.0}}) == ["y", "x"]


def test_expected_room_value_and_opportunity():
    curve = [80.0, 50.0, 20.0, 1.0]
    exp = room.expected_prices(["a", "b", "c"], curve)
    assert exp == {"a": 80.0, "b": 50.0, "c": 20.0}
    val = room.room_values({"a": 2, "b": 3, "c": 1, "d": 9}, curve)
    assert val == {"a": 50.0, "b": 20.0, "c": 80.0, "d": 1.0}
    opp = room.opportunity(val, exp)
    assert opp["c"] == 60.0 and opp["a"] == -30.0 and opp["d"] == 0.0
