"""Simulated H2H value (own model, research note `docs/modules/valuation-models-research.md`, 2026-10-13).

A player's value = his share of category matchups won when he joins many random fantasy teams that
play every fantasy week against other random teams. No z, no SD: the nonlinear, saturating worth of a
category win is in the simulation itself.

Weekly lines are expected lines, not samples: per-game stats x the team's games in that fantasy week
x availability (projected or real GP / 82 on the totals basis; 1 on the per-game basis). Deterministic
(no week-to-week noise yet). Teams are drawn from the top `pool_size` players by expected fantasy
points. Every candidate is scored in every context he is not already part of; the mean over contexts
is his value. 600 contexts x 11 opponents take about 3 seconds with numpy.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.analytics.valuation.core import Settings, basis_stats

STAT_KEYS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
_I = {k: i for i, k in enumerate(STAT_KEYS)}


@dataclass(frozen=True)
class SimInputs:
    weeks: tuple[date, ...]  # Mondays of the fantasy weeks
    team_games: dict[str, tuple[int, ...]]  # NBA team -> games in each week
    team_of: dict[object, str]  # player -> NBA team; players without a team get the mean schedule
    team_size: int = 12  # players per fantasy team (non-IL slots)
    contexts: int = 600
    opponents: int = 11
    seed: int = 1
    season_games: int = 82


def cat_lines(x: np.ndarray) -> np.ndarray:
    """(..., 11) weekly sums -> (..., 9) category values in CATEGORIES order; TO negated; 0 when no attempts."""
    fga, fta = x[..., _I["fga"]], x[..., _I["fta"]]
    fg = np.divide(x[..., _I["fgm"]], fga, out=np.zeros_like(fga), where=fga > 0)
    ft = np.divide(x[..., _I["ftm"]], fta, out=np.zeros_like(fta), where=fta > 0)
    return np.stack([fg, ft, x[..., _I["tpm"]], x[..., _I["pts"]], x[..., _I["reb"]], x[..., _I["ast"]],
                     x[..., _I["stl"]], x[..., _I["blk"]], -x[..., _I["tov"]]], axis=-1)


def expected_lines(rows: dict, basis: str, inputs: SimInputs) -> tuple[list, np.ndarray]:
    """(players with gp > 0, E (P, weeks, 11) expected weekly lines)."""
    n_weeks = len(inputs.weeks)
    if inputs.team_games:
        mean_games = np.mean([g[:n_weeks] for g in inputs.team_games.values()], axis=0)
    else:
        mean_games = np.full(n_weeks, 3.5)
    players = [p for p, r in rows.items() if r["gp"] > 0]
    e = np.zeros((len(players), n_weeks, len(STAT_KEYS)))
    for i, p in enumerate(players):
        r = rows[p]
        per_game = basis_stats(r, "per_game")
        avail = min(r["gp"] / inputs.season_games, 1.0) if basis == "totals" else 1.0
        games = inputs.team_games.get(inputs.team_of.get(p))
        g = np.array(games[:n_weeks], dtype=float) if games is not None else mean_games
        e[i] = np.array([per_game[k] for k in STAT_KEYS])[None, :] * (avail * g)[:, None]
    return players, e


def _fantasy_points(e: np.ndarray) -> np.ndarray:
    """Season sum of Yahoo-style fantasy points per player, to pick the draftable pool."""
    s = e.sum(axis=1)
    return s[:, _I["pts"]] + 1.2 * s[:, _I["reb"]] + 1.5 * s[:, _I["ast"]] + 3 * s[:, _I["stl"]] + 3 * s[:, _I["blk"]] - s[:, _I["tov"]]


def score_candidates(e: np.ndarray, base: np.ndarray, opponents: list[np.ndarray]) -> np.ndarray:
    """Category win share of every candidate added to `base` (11 players) against the opponent teams."""
    b = e[base].sum(axis=0)  # (weeks, 11)
    x = cat_lines(b[None] + e)  # (P, weeks, 9)
    o = cat_lines(np.stack([e[r].sum(axis=0) for r in opponents]))  # (K, weeks, 9)
    win = (x[:, None] > o[None]).astype(np.float32) + 0.5 * (x[:, None] == o[None])  # (P, K, weeks, 9)
    return win.mean(axis=(1, 2, 3))


def simulate(rows: dict, settings: Settings, inputs: SimInputs, pool_size: int = 144, team_size: int | None = None) -> dict:
    """Player -> value: category wins above 50%, per 100 matchups."""
    team_size = team_size or inputs.team_size
    players, e = expected_lines(rows, settings.basis, inputs)
    n = len(players)
    pool = np.argsort(-_fantasy_points(e))[:pool_size]
    need = team_size - 1 + team_size * inputs.opponents
    if len(pool) < need:
        raise ValueError(f"pool of {len(pool)} players is too small for {inputs.opponents} opponents of {team_size}")
    rng = np.random.default_rng(inputs.seed)
    acc = np.zeros(n)
    count = np.zeros(n)
    for _ in range(inputs.contexts):
        perm = rng.permutation(pool)
        base = perm[: team_size - 1]
        opps = [perm[team_size - 1 + team_size * k: team_size - 1 + team_size * (k + 1)] for k in range(inputs.opponents)]
        share = score_candidates(e, base, opps)
        mask = np.ones(n, dtype=bool)
        mask[base] = False
        acc[mask] += share[mask]
        count[mask] += 1
    value = (acc / np.maximum(count, 1) - 0.5) * 100.0
    return {p: float(value[i]) for i, p in enumerate(players)}


def whatif(rows: dict, basis: str, inputs: SimInputs, my: list, opponents: list[list], candidate) -> dict:
    """Draft-day question: what does `candidate` do to my team against the other teams, week by week?

    Teams are the rosters so far (partial during a draft; an empty team has a zero line and loses, as the
    live H2H matrix does). Shares in percent. per_cat and per_opp follow the input order.
    """
    players, e = expected_lines(rows, basis, inputs)
    idx = {p: i for i, p in enumerate(players)}
    if candidate not in idx:
        raise ValueError("candidate has no games in this base")
    zero = np.zeros(e.shape[1:])

    def team(pks):
        ids = [idx[p] for p in pks if p in idx]
        return e[ids].sum(axis=0) if ids else zero

    mine = team(my)
    opp = np.stack([team(o) for o in opponents]) if opponents else np.zeros((0, *zero.shape))
    o_lines = cat_lines(opp)

    def score(x):
        if not len(opp):
            return {"cat_share": 50.0, "match_share": 50.0, "per_cat": [50.0] * 9, "per_opp": []}
        lines = cat_lines(x)[None]
        win = (lines > o_lines).astype(float) + 0.5 * (lines == o_lines)  # (K, W, 9)
        cats = win.sum(-1)
        match = (cats > 4.5) + 0.5 * (cats == 4.5)
        return {"cat_share": 100 * float(win.mean()), "match_share": 100 * float(match.mean()),
                "per_cat": (100 * win.mean(axis=(0, 1))).tolist(), "per_opp": (100 * win.mean(axis=(1, 2))).tolist()}

    before, after = score(mine), score(mine + e[idx[candidate]])
    delta = {"cat_share": after["cat_share"] - before["cat_share"], "match_share": after["match_share"] - before["match_share"],
             "per_cat": [a - b for a, b in zip(after["per_cat"], before["per_cat"])],
             "per_opp": [a - b for a, b in zip(after["per_opp"], before["per_opp"])]}
    return {"before": before, "after": after, "delta": delta, "weeks": len(inputs.weeks)}
