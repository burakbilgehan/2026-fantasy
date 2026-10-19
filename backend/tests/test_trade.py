from datetime import date

from app.analytics import season_sim as ss
from app.analytics import trade as tr


def row(pk, ours, yahoo, pts=10.0, pos="G"):
    stats = {"gp": 80, "fgm": 400, "fga": 800, "ftm": 100, "fta": 120, "tpm": 80, "pts": pts * 80, "reb": 300,
             "ast": 200, "stl": 60, "blk": 30, "tov": 100}
    return {"player_id": pk, "name": f"P{pk}", "team": "AAA", "positions": [pos], "stats": stats, "total": ours,
            "dollars": ours, "market": {"yahoo_auction_value": yahoo}}


def ctx():
    rows = {pk: row(pk, ours=pk, yahoo=20 - pk) for pk in range(1, 13)}
    rows[99] = row(99, ours=9.5, yahoo=1)  # best free agent by our value
    rows[98] = row(98, ours=0.5, yahoo=5)  # best free agent by Yahoo value
    rosters = {1: [1, 2, 3, 4], 2: [5, 6, 7, 8], 3: [9, 10, 11, 12]}
    w = ss.Week(1, date(2026, 10, 20), date(2026, 10, 21))
    return tr.Context(rows=rows, rosters=rosters, names={1: "me", 2: "b", 3: "c"}, me=1, weeks=[w],
                      matchups={1: [(1, 2)]}, plays={date(2026, 10, 20): {"AAA"}})


def test_two_for_one_keeps_roster_sizes():
    c = ctx()
    t = tr.apply_trade(c, give=[1, 2], get=[5], partner=2)
    assert len(t["mine"]) == 4 and len(t["theirs"]) == 4
    assert t["my_add"] == [99]  # I add by our value
    assert t["their_drop"] == [8]  # they drop their lowest Yahoo value (P8: 12) among the players they keep
    assert 1 in t["theirs"] and 2 in t["theirs"]


def test_one_for_two_drops_my_weakest_and_they_add_by_yahoo():
    c = ctx()
    t = tr.apply_trade(c, give=[4], get=[5, 6], partner=2)
    assert t["my_drop"] == [1]  # our lowest value among the players I keep
    assert t["their_add"] == [98]  # the best free agent by Yahoo value
    assert len(t["mine"]) == 4 and len(t["theirs"]) == 4


def test_fa_only_baseline():
    c = ctx()
    assert sorted(tr.fa_only(c, 1)) == [2, 3, 4, 99]


def test_accept_label_trusts_yahoo_first():
    assert tr.accept_label(1, 0.0) == "likely"
    assert tr.accept_label(1, -0.05) == "maybe"
    assert tr.accept_label(-2, 0.0) == "maybe"
    assert tr.accept_label(-5, 0.0) == "hard"


def test_team_line_modes():
    c = ctx()
    avg, tot = tr.team_line(c.rows, [1, 2], "avg"), tr.team_line(c.rows, [1, 2], "total")
    assert avg["pts"] == 10.0 and tot["pts"] == 1600
    assert avg["fg_pct"] == tot["fg_pct"] == 0.5


def test_evaluate_and_find_run():
    c = ctx()
    e = tr.evaluate(c, [1], [5], 2)
    assert set(e["me"]) >= {"avg", "total", "sim_before", "sim_after"}
    assert len(e["fixture_after"]) == 1
    res = tr.find(c, give=[1], get=[], improve=[], max_size=2, min_their_yahoo=-100)
    assert res and all(r["partner"] in (2, 3) for r in res)


def test_value_changes_count_drops_and_free_agents():
    c = ctx()
    t = tr.apply_trade(c, give=[4], get=[5, 6], partner=2)  # 1-for-2: I drop P1, they add FA 98
    v = tr.value_changes(c, [4], [5, 6], t)
    assert v["ours"] == 5 + 6 - 4 - 1
    assert v["their_yahoo"] == 16 + 5 - 15 - 14
    t = tr.apply_trade(c, give=[1, 2], get=[5], partner=2)  # 2-for-1: I add FA 99, they drop P8
    v = tr.value_changes(c, [1, 2], [5], t)
    assert v["ours"] == 5 + 9.5 - 1 - 2
    assert v["their_yahoo"] == 19 + 18 - 15 - 12


def test_near_ties_drop_by_position_balance():
    c = ctx()
    # I give a guard (P4) and get a forward and a center: my two weakest (P1 G, P2 C) are near ties.
    c.rows[2]["positions"] = ["C"]
    c.rows[5]["positions"], c.rows[6]["positions"] = ["F"], ["C"]
    t = tr.apply_trade(c, give=[4], get=[5, 6], partner=2)
    assert t["my_drop"] == [2]  # the center goes, not the weaker guard: the trade brought a center


def test_clear_weakest_is_dropped_whatever_the_position():
    c = ctx()
    c.rows[1]["dollars"] = -10  # far below everyone
    c.rows[2]["positions"] = ["C"]
    c.rows[5]["positions"], c.rows[6]["positions"] = ["F"], ["C"]
    t = tr.apply_trade(c, give=[4], get=[5, 6], partner=2)
    assert t["my_drop"] == [1]
