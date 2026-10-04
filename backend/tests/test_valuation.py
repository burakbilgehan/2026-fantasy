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


def test_minus1_and_durant_drop_the_worst_category():
    s = Settings(pool=None)
    z, ztot = value(POOL, MODELS["zscore"].total, s)
    _, m1 = value(POOL, MODELS["minus1"].total, s)
    _, du = value(POOL, MODELS["durant"].total, s)
    for p, zp in z.items():
        assert m1[p] == pytest.approx(ztot[p] - min(zp.values()))
        eight = [zp[c] for c in CATEGORIES if c != "tov"]
        assert du[p] == pytest.approx(sum(eight) - min(eight))
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
