import math
from datetime import date, timedelta
from itertools import combinations

import pytest

from app.analytics.h2h_backtest import all_play, best_roster, matchup, team_weeks
from app.analytics.valuation import CATEGORIES, MODELS, Settings, g_weights, reliability, run, to_dollars, value
from app.analytics.valuation.dollars import savor


def _row(gp, fgm, fga, ftm, fta, tpm, pts, reb, ast, stl, blk, tov):
    return dict(gp=gp, fgm=fgm, fga=fga, ftm=ftm, fta=fta, tpm=tpm, pts=pts, reb=reb, ast=ast, stl=stl, blk=blk, tov=tov)


# Per-game lines x 70 games. "big" shoots badly from the line, "guard" turns it over a lot.
POOL = {
    "star": _row(70, 700, 1400, 420, 490, 140, 1960, 700, 560, 105, 70, 210),
    "big": _row(70, 560, 980, 140, 350, 0, 1260, 840, 140, 56, 175, 140),
    "guard": _row(70, 490, 1120, 280, 315, 210, 1470, 280, 630, 84, 21, 280),
    "wing": _row(70, 350, 770, 140, 168, 140, 980, 350, 175, 70, 35, 84),
    "bench": _row(70, 210, 490, 70, 91, 70, 560, 210, 140, 35, 14, 70),
    "dnp": _row(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
}


def test_zscore_sums_to_zero_over_pool_and_skips_dnp():
    z, totals = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    assert "dnp" not in z
    for c in CATEGORIES:
        assert sum(zp[c] for zp in z.values()) == pytest.approx(0, abs=1e-9)
    assert max(totals, key=totals.get) == "star"


def test_turnovers_count_negative():
    z, _ = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    assert z["guard"]["tov"] < 0 < z["bench"]["tov"]


def test_percent_is_volume_weighted():
    rows = {
        "volume": _row(1, 50, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        "few": _row(1, 5, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        "bad": _row(1, 30, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    }
    z, _ = value(rows, MODELS["zscore"].total, Settings(pool=None))
    # same 50% rate, more attempts above the pool rate = more FG% impact
    assert z["volume"]["fg_pct"] > z["few"]["fg_pct"] > z["bad"]["fg_pct"]


def test_per_game_basis_ignores_games_played():
    rows = dict(POOL, half=dict(POOL["star"], **{k: v / 2 for k, v in POOL["star"].items()}))
    _, tot = value(rows, MODELS["zscore"].total, Settings(basis="totals", pool=None))
    _, pg = value(rows, MODELS["zscore"].total, Settings(basis="per_game", pool=None))
    assert tot["half"] < tot["star"]
    assert pg["half"] == pytest.approx(pg["star"])


def test_minus1_drops_the_worst_category():
    s = Settings(pool=None)
    z, ztot = value(POOL, MODELS["zscore"].total, s)
    _, m1 = value(POOL, MODELS["minus1"].total, s)
    for p, zp in z.items():
        assert m1[p] == pytest.approx(ztot[p] - min(zp.values()))
    # the big man's FT% is his worst category; Minus-1 removes it
    assert min(z["big"], key=z["big"].get) == "ft_pct"


def test_punt_without_categories_equals_zscore_and_removes_them():
    _, zt = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    _, pt = value(POOL, MODELS["punt"].total, Settings(pool=None))
    assert pt == pytest.approx(zt)
    z, pft = value(POOL, MODELS["punt"].total, Settings(pool=None, punt=frozenset({"ft_pct"})))
    assert pft["big"] == pytest.approx(zt["big"] - z["big"]["ft_pct"])


def test_gscore_with_unit_weights_equals_zscore():
    _, zt = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    _, gt = value(POOL, MODELS["gscore"].total, Settings(pool=None, g_weights=dict.fromkeys(CATEGORIES, 1.0)))
    assert gt == pytest.approx(zt)
    with pytest.raises(ValueError):
        value(POOL, MODELS["gscore"].total, Settings(pool=None))


def test_pool_setting_changes_reference():
    _, all_ = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    _, top3 = value(POOL, MODELS["zscore"].total, Settings(pool=3))
    assert top3["bench"] < all_["bench"]  # a stronger pool makes a weak player look worse


def test_plain_dollars_share_the_budget():
    totals = {i: float(100 - i) for i in range(200)}
    usd = to_dollars(totals, n_drafted=144, budget=2400)
    assert sum(usd.values()) == pytest.approx(2400)
    assert usd[143] == pytest.approx(1 + (totals[143] - totals[144]) * 2256 / sum(totals[i] - totals[144] for i in range(144)))
    assert usd[144] == 0 and usd[0] > usd[1]


def test_savor_is_monotonic_keeps_the_total_and_favors_stars():
    assert savor(0, 10) == 0
    xs = [savor(d, 10) for d in range(0, 80)]
    assert all(b > a for a, b in zip(xs, xs[1:]))
    totals = {i: float(100 - i) for i in range(200)}
    plain = to_dollars(totals)
    sv = to_dollars(totals, method="savor")
    assert sum(sv.values()) == pytest.approx(2400)
    assert sv[0] > plain[0] and sv[140] < plain[140]


def test_run_returns_rank_and_dollars():
    out = run(POOL, "zscore", Settings(pool=None), n_drafted=3, budget=30)
    assert out["star"]["rank"] == 1
    assert sum(r["dollars"] for r in out.values()) == pytest.approx(30)


def _logs(player, season, per_week_pts, weeks=10):
    start = date(2024, 10, 21)  # a Monday
    out = []
    for w in range(weeks):
        pts = per_week_pts[w % len(per_week_pts)]
        out.append(dict(player=player, season=season, game_date=start + timedelta(weeks=w), min=30,
                        fgm=5, fga=10, ftm=2, fta=3, tpm=1, pts=pts, reb=5, ast=3, stl=1, blk=1, tov=2))
    return out


def test_g_weights_shrink_noisy_categories():
    logs = _logs("a", "2024-25", [30]) + _logs("b", "2024-25", [10]) + _logs("c", "2024-25", [20])
    w = g_weights(logs, pool_size=3)
    assert w["pts"] == pytest.approx(1.0)  # no week-to-week noise: same as z-score
    noisy = _logs("a", "2024-25", [10, 50]) + _logs("b", "2024-25", [0, 20]) + _logs("c", "2024-25", [5, 35])
    assert g_weights(noisy, pool_size=3)["pts"] < 1.0


def test_reliability():
    seasons = ["2023-24", "2024-25", "2025-26"]
    assert reliability({"2023-24": 82, "2024-25": 41, "2025-26": 82}, seasons) == pytest.approx(5 / 6)
    assert reliability({"2025-26": 41}, seasons) == pytest.approx(0.5)  # rookie: earlier seasons skipped
    assert reliability({"2023-24": 82}, seasons) == pytest.approx(1 / 3)  # missed two full seasons
    assert reliability({}, seasons) is None


def test_best_roster_matches_brute_force():
    cands = {i: (float((i * 37) % 23), 1 + (i * 11) % 9) for i in range(10)}
    picked = best_roster(cands, slots=3, budget=10)
    best = max((c for c in combinations(cands, 3) if sum(cands[p][1] for p in c) <= 10),
               key=lambda c: sum(cands[p][0] for p in c))
    assert len(picked) == 3 and sum(cands[p][1] for p in picked) <= 10
    assert sum(cands[p][0] for p in picked) == pytest.approx(sum(cands[p][0] for p in best))


def test_matchup_and_all_play():
    base = dict(fgm=40, fga=100, ftm=20, fta=25, tpm=10, pts=120, reb=50, ast=30, stl=8, blk=5, tov=15)
    better = dict(base, pts=130, tov=12)  # wins PTS and TO, ties 7
    assert matchup(better, base) == (2 + 7 / 2, 1.0)
    assert matchup(base, base) == (4.5, 0.5)
    weeks = ["w1"]
    tw = team_weeks(["x"], {"x": {"w1": better}}, weeks)
    ow = team_weeks(["y"], {"y": {"w1": base}}, weeks)
    assert all_play(tw, [ow], weeks) == (pytest.approx(5.5 / 9), 1.0)


# --- 2026-10-13: Yeo-Johnson, DURANT H2H (published formula), kappa, simulation ---

def test_yeo_johnson_matches_scipy_reference():
    from app.analytics.valuation.transform import fit_lambda, yeo_johnson

    # scipy.stats.yeojohnson on this sample (checked 2026-10-13): lambda 0.1800 on a gamma(4, 4) draw
    # is not reproducible without the draw, so use closed-form cases instead.
    assert yeo_johnson([0.0, 3.0], 1.0) == pytest.approx([0.0, 3.0])  # lambda 1 = identity
    assert yeo_johnson([3.0], 0.0) == pytest.approx([math.log(4.0)])
    assert yeo_johnson([-3.0], 2.0) == pytest.approx([-math.log(4.0)])
    assert yeo_johnson([-3.0], 1.0) == pytest.approx([-3.0])
    # a right-skewed sample gets lambda below 1 (compressing the tail); a symmetric one stays near 1
    skewed = [0.1, 0.2, 0.2, 0.3, 0.4, 0.5, 0.6, 0.9, 1.5, 2.5, 4.0, 7.0]
    assert fit_lambda(skewed) < 0.6
    symmetric = [-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3]
    assert 0.8 < fit_lambda(symmetric) < 1.2


def test_transform_setting_reduces_an_outlier_category():
    # with the transform, the big man's blocks z shrinks relative to the plain z
    _, _ = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    z_plain, _ = value(POOL, MODELS["zscore"].total, Settings(pool=None))
    z_yj, _ = value(POOL, MODELS["zscore"].total, Settings(pool=None, transform="yeo_johnson"))
    assert z_yj["big"]["blk"] < z_plain["big"]["blk"]
    assert z_yj["guard"]["tov"] < 0  # turnovers still count negative


def test_durant_h2h_weights_no_turnovers_minus_one():
    from app.analytics.valuation.models import DURANT_H2H_WEIGHTS

    z = {c: 1.0 for c in CATEGORIES}
    z["ft_pct"], z["tov"] = -2.0, -5.0
    # weighted sum of the 8 non-TO categories, minus the worst weighted one (FT%: 0.6 x -2 = -1.2)
    expect = sum(DURANT_H2H_WEIGHTS[c] * z[c] for c in CATEGORIES if c != "tov") + 1.2
    assert MODELS["durant"].total(z, Settings()) == pytest.approx(expect)
    assert MODELS["durant"].transform == "yeo_johnson"
    # the broad DURANT: all eight at 1.0, turnovers at 0.5, nothing removed
    assert MODELS["durant_all"].total(z, Settings()) == pytest.approx(7 * 1.0 - 2.0 + 0.5 * -5.0)


def test_g_weights_kappa_uses_roster_size():
    noisy = _logs("a", "2024-25", [10, 50]) + _logs("b", "2024-25", [0, 20]) + _logs("c", "2024-25", [5, 35])
    w12 = g_weights(noisy, pool_size=3, roster_size=12)["pts"]
    w13 = g_weights(noisy, pool_size=3, roster_size=13)["pts"]
    assert w12 < w13 < 1.0  # a smaller roster: larger kappa, more shrinkage


def test_simulation_prefers_the_better_player_and_counts_games():
    from datetime import date as _date

    from app.analytics.valuation.simulate import SimInputs, simulate

    weeks = tuple(_date(2026, 10, 19) + timedelta(weeks=i) for i in range(4))
    inputs = SimInputs(weeks=weeks, team_games={"A": (3, 4, 3, 4), "B": (4, 4, 4, 4)},
                       team_of={p: "A" for p in POOL} | {"wing": "B", "half": "A"}, contexts=40, opponents=2, seed=1)
    rows = dict(POOL)
    rows["half"] = dict(POOL["star"], gp=35, **{k: v / 2 for k, v in POOL["star"].items() if k != "gp"})
    share = simulate(rows, Settings(basis="totals"), inputs, pool_size=6, team_size=2)
    assert share["star"] > share["bench"]
    assert share["star"] > share["half"]  # same per-game line, half the games: fewer weekly wins
    assert "dnp" not in share
    # per game ignores availability: the same per-game line gives the same expected weekly lines
    from app.analytics.valuation.simulate import expected_lines

    players, e = expected_lines(rows, "per_game", inputs)
    assert e[players.index("half")] == pytest.approx(e[players.index("star")])
    players, e = expected_lines(rows, "totals", inputs)
    assert e[players.index("half")].sum() == pytest.approx(e[players.index("star")].sum() / 2)
    assert e[players.index("wing")].sum() > 0  # team B: 4 games every week


def test_whatif_reports_gains_and_losses_by_category():
    from datetime import date as _date

    from app.analytics.valuation.simulate import SimInputs, whatif

    weeks = tuple(_date(2026, 10, 19) + timedelta(weeks=i) for i in range(3))
    inputs = SimInputs(weeks=weeks, team_games={"A": (3, 4, 3)}, team_of={p: "A" for p in POOL}, team_size=2)
    # my team: the guard. Opponents: the wing alone, and the bench player alone. Candidate: the big.
    r = whatif(POOL, "totals", inputs, my=["guard"], opponents=[["wing"], ["bench"]], candidate="big")
    assert r["weeks"] == 3 and len(r["before"]["per_opp"]) == 2
    assert r["after"]["cat_share"] >= r["before"]["cat_share"]
    i_ft, i_blk = CATEGORIES.index("ft_pct"), CATEGORIES.index("blk")
    assert r["delta"]["per_cat"][i_blk] >= 0  # the big adds blocks
    assert r["delta"]["per_cat"][i_ft] <= 0  # and drags the free-throw rate down
    empty = whatif(POOL, "totals", inputs, my=[], opponents=[], candidate="big")
    assert empty["delta"]["cat_share"] == 0
    with pytest.raises(ValueError):
        whatif(POOL, "totals", inputs, my=["guard"], opponents=[["wing"]], candidate="dnp")


def test_room_auction_respects_money_slots_and_second_price():
    import numpy as np

    from app.analytics.draftsim import Manager, auction

    rng = np.random.default_rng(1)
    pool = {f"p{i}": 60 - i for i in range(30)}  # 30 players, values 60 .. 31
    managers = [Manager("a", "x", dict(pool), money=100, slots=5, noise=0.0),
                Manager("b", "x", {p: v * 0.5 for p, v in pool.items()}, money=100, slots=5, noise=0.0)]
    log = auction(managers, list(pool), rng)
    assert all(m.slots == 0 and len(m.roster) == 5 for m in managers)
    assert all(m.money >= 0 for m in managers) and len(log) == 10
    first = log[0]
    assert first["price"] == first["second"] + 1 or first["price"] == 1  # pays the second bid plus one
    assert all(r["price"] >= 1 for r in log)


def test_room_season_rewards_the_stronger_roster():
    from datetime import date as _date

    import numpy as np

    from app.analytics.draftsim import play, round_robin
    from app.analytics.valuation.simulate import SimInputs

    assert all(len(r) == 6 for r in round_robin(12)) and len(round_robin(12)) == 11
    weeks = tuple(_date(2026, 10, 19) + timedelta(weeks=i) for i in range(6))
    inputs = SimInputs(weeks=weeks, team_games={"A": (3, 4, 3, 4, 3, 4)}, team_of={p: "A" for p in POOL}, team_size=2)
    rosters = [["star", "big"], ["guard", "wing"], ["bench"], []]
    out = play(rosters, POOL, "totals", inputs, np.random.default_rng(2), seasons=50, playoff_weeks=2, playoff_teams=4)
    assert out["weeks"] == 6 and out["games"] == 4
    assert out["cat_share"][0] > out["cat_share"][1] > out["cat_share"][3]
    assert abs(sum(out["titles"]) - 100) < 1e-6 and out["titles"][0] > out["titles"][3]
    assert abs(sum(out["wins"]) - 4 * 2) < 1e-6  # 4 regular weeks, 2 matchups per week
