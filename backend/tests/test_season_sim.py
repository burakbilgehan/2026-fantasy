from datetime import date

from app.analytics import season_sim as ss


def p(pk, pos, value, avail=1.0, pts=10.0, team="AAA"):
    per_game = tuple(pts if k == "pts" else (1.0 if k in ("fga", "fta") else 0.0) for k in ss.STAT_KEYS)
    return ss.SimPlayer(pk=pk, team=team, positions=tuple(pos), value=value, per_game=per_game, availability=avail)


PTS = ss.STAT_KEYS.index("pts")


def test_ten_slots_best_first():
    players = [p(i, "G", value=i) for i in range(12)]  # 12 guards, all healthy
    sums, used, avail = ss.day_line(players)
    assert used == 6  # 3 G slots + 3 Util; F and C slots stay empty
    assert avail == 12
    assert sums[PTS] == 60


def test_positions_limit_the_lineup():
    players = [p(i, "C", value=10 - i) for i in range(6)]
    _, used, _ = ss.day_line(players)
    assert used == 4  # 1 C + 3 Util


def test_missed_games_go_to_the_next_player():
    star = p(1, "G", value=10, avail=0.6, pts=30)
    bench = [p(i, "G", value=1, pts=10) for i in range(2, 8)]  # 6 healthy guards for 6 G/Util slots
    sums, used, _ = ss.day_line([star, *bench])
    assert used == 6
    assert abs(sums[PTS] - (0.6 * 30 + 5.4 * 10)) < 1e-9


def test_multi_position_player_does_not_crowd_out_guards():
    gf = p(1, "GF", value=10)
    guards = [p(i, "G", value=5) for i in range(2, 5)]
    _, used, _ = ss.day_line([gf, *guards])
    assert used == 4  # G,F player goes to F, the three guards keep the G slots


def test_compare_turnovers_lower_wins():
    a = {c: 1.0 for c in ss.CATS} | {"tov": 1.0}
    b = {c: 1.0 for c in ss.CATS} | {"tov": 2.0, "pts": 2.0}
    r = ss.compare(a, b)
    assert r[ss.CATS.index("tov")] == 1
    assert r[ss.CATS.index("pts")] == -1
    assert r.count(0) == 7


def test_season_scores_scheduled_matchups():
    w = ss.Week(1, date(2026, 10, 20), date(2026, 10, 21))
    strong = [p(1, "G", value=5, pts=30)]
    weak = [p(2, "G", value=5, pts=10)]
    out = ss.season({1: strong, 2: weak}, [w], {date(2026, 10, 20): {"AAA"}}, {1: [(1, 2)]})
    assert out["record"][1][0] == 1  # wins PTS; every other category ties
    assert out["record"][2][1] == 1
    assert out["lines"][1][0]["used"] == 1
