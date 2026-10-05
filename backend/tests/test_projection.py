from app.analytics.projection.engine import COMPONENTS, Params, Season, project, project_gp, rates
from app.analytics.projection.data import normalise_position, season_age
from datetime import date

PRIOR = {c: 0.1 for c in COMPONENTS} | {"fg_pct": 0.45, "ft_pct": 0.75}
STATS = {"fgm": 500, "fga": 1000, "ftm": 160, "fta": 200, "tpm": 150, "reb": 400, "ast": 300,
         "stl": 80, "blk": 40, "tov": 150}


def season(name="2025-26", gp=70, minutes=2000.0):
    return Season(season=name, gp=gp, min=minutes, stats=dict(STATS))


def test_no_history_is_prior():
    assert rates([], PRIOR, Params()) == PRIOR


def test_k_zero_is_raw_rate_and_large_k_is_prior():
    p0 = Params(k={c: 0.0 for c in COMPONENTS})
    r = rates([season()], PRIOR, p0)
    assert abs(r["fga"] - 0.5) < 1e-9 and abs(r["fg_pct"] - 0.5) < 1e-9
    big = Params(k={c: 1e9 for c in COMPONENTS})
    assert abs(rates([season()], PRIOR, big)["reb"] - 0.1) < 1e-6


def test_newest_season_full_weight():
    # Weights (1, 0, 0): older seasons do not count, the newest one counts at full minutes.
    p = Params(season_weights=(1.0, 0.0, 0.0), k={c: 2000.0 for c in COMPONENTS})
    one = rates([season()], PRIOR, p)
    three = rates([season(), season("2024-25", minutes=500), season("2023-24", minutes=500)], PRIOR, p)
    assert one == three


def test_points_identity_and_minutes():
    r = rates([season()], PRIOR, Params(k={c: 0.0 for c in COMPONENTS}))
    line = project(r, mpg=30.0, gp=60.0)
    assert abs(line["min"] - 1800) < 1e-9
    assert abs(line["pts"] - (2 * line["fgm"] + line["ftm"] + line["tpm"])) < 1e-9


def test_multiplier_scales_component():
    r = rates([season()], PRIOR, Params())
    a = project(r, 30.0, 60.0)
    b = project(r, 30.0, 60.0, multipliers={"ast": 1.2})
    assert abs(b["ast"] / a["ast"] - 1.2) < 1e-9 and b["pts"] == a["pts"]


def test_gp_games_out_and_cap():
    p = Params(gp_a=0.3, gp_b=0.6)
    full = project_gp([season(gp=82)], p)
    assert abs(full - 82 * 0.9) < 1e-9
    assert abs(project_gp([season(gp=82)], p, games_out=10, late_games_out=5) - (full - 15)) < 1e-9
    assert project_gp([season(gp=82)], p, games_out=500) == 0.0


def test_age_and_position():
    assert season_age(date(1995, 2, 19), "2026-27") == 31
    assert season_age(date(1995, 2, 2), "2026-27") == 31
    assert season_age(date(1995, 1, 31), "2026-27") == 32
    assert normalise_position("G-F") == "G,F" and normalise_position("PF") == "F" and normalise_position("") is None
