"""Empirical marginal H2H value (MWV) per season. Throwaway research code.

Context = an 11-player base team B plus K opponent teams. Every candidate p is added to B;
the team's weekly 9-cat line is compared with every opponent in every fantasy week.
MWV[p] = mean over contexts of the category win share; also the matchup win share.
Synthetic contexts: B and the opponents are random 12-player teams from the pool (top 144 by minutes).
Real contexts (2025-26): B = a real draft roster minus one member; opponents = the other 11 real rosters.
"""
import sys, time
import numpy as np
from vdata import *

I = {s: i for i, s in enumerate(STATS)}


def cat_lines(X):
    """X (..., 11) weekly sums -> (..., 9) category values, TO negated, pct = 0 when no attempts."""
    fga, fta = X[..., I['fga']], X[..., I['fta']]
    fg = np.divide(X[..., I['fgm']], fga, out=np.zeros_like(fga), where=fga > 0)
    ft = np.divide(X[..., I['ftm']], fta, out=np.zeros_like(fta), where=fta > 0)
    return np.stack([fg, ft, X[..., I['tpm']], X[..., I['pts']], X[..., I['reb']], X[..., I['ast']],
                     X[..., I['stl']], X[..., I['blk']], -X[..., I['tov']]], axis=-1)


def score_candidates(W, base_idx, opp_rosters):
    """W (P, nw, 11). base_idx: 11 players. opp_rosters: list of index arrays.
    Returns cat share (P,), match share (P,), per-category share (P, 9)."""
    B = W[base_idx].sum(axis=0)                      # (nw, 11)
    X = cat_lines(B[None] + W)                        # (P, nw, 9)
    O = cat_lines(np.stack([W[r].sum(axis=0) for r in opp_rosters]))  # (K, nw, 9)
    win = (X[:, None] > O[None]).astype(np.float32) + 0.5 * (X[:, None] == O[None])  # (P, K, nw, 9)
    cats = win.sum(axis=-1)                           # (P, K, nw)
    match = (cats > 4.5) + 0.5 * (cats == 4.5)
    return win.mean(axis=(1, 2, 3)), match.mean(axis=(1, 2)), win.mean(axis=(1, 2))


def synthetic(season, n_ctx=600, pool_size=144, n_opp=11, seed=1):
    players, weeks, W, G = weekly(season)
    tot = season_totals(season)
    minutes = np.array([tot.get(p, {}).get('min', 0) for p in players])
    pool = np.argsort(-minutes)[:pool_size]
    rng = np.random.default_rng(seed)
    P = len(players)
    acc = np.zeros(P); accm = np.zeros(P); accc = np.zeros((P, 9)); n = np.zeros(P)
    t0 = time.time()
    for c in range(n_ctx):
        perm = rng.permutation(pool)
        base = perm[:11]
        opps = [perm[11 + 12 * k: 11 + 12 * (k + 1)] for k in range(n_opp)]
        cs, ms, cc = score_candidates(W, base, opps)
        mask = np.ones(P, bool); mask[base] = False
        acc[mask] += cs[mask]; accm[mask] += ms[mask]; accc[mask] += cc[mask]; n[mask] += 1
    print(f'{season}: {n_ctx} contexts, {len(weeks)} weeks, {P} players, {time.time() - t0:.0f}s', file=sys.stderr)
    return players, acc / n, accm / n, accc / n[:, None]


def real_2526(n_opp=11):
    season = '2025-26'
    players, weeks, W, G = weekly(season)
    idx = {p: i for i, p in enumerate(players)}
    picks = past_draft(season)
    rosters = {}
    for pk, team, price in picks:
        if pk in idx:
            rosters.setdefault(team, []).append(idx[pk])
    teams = sorted(rosters)
    P = len(players)
    acc = np.zeros(P); accm = np.zeros(P); accc = np.zeros((P, 9)); n = np.zeros(P)
    per_team = {}
    for t in teams:
        opps = [np.array(rosters[o]) for o in teams if o != t]
        team_acc = np.zeros(P); team_n = np.zeros(P)
        for drop in rosters[t]:
            base = np.array([x for x in rosters[t] if x != drop])
            cs, ms, cc = score_candidates(W, base, opps)
            mask = np.ones(P, bool); mask[base] = False
            acc[mask] += cs[mask]; accm[mask] += ms[mask]; accc[mask] += cc[mask]; n[mask] += 1
            team_acc[mask] += cs[mask]; team_n[mask] += 1
        per_team[t] = team_acc / np.maximum(team_n, 1)
    print(f'{season} real rosters: {len(teams)} teams, {sum(len(r) for r in rosters.values())} rostered players found', file=sys.stderr)
    return players, acc / n, accm / n, accc / n[:, None], per_team


if __name__ == '__main__':
    out = {}
    for season in SEASONS:
        players, cs, ms, cc = synthetic(season)
        out[season] = dict(players=np.array(players), cat=cs, match=ms, percat=cc)
    players, cs, ms, cc, per_team = real_2526()
    out['2025-26-real'] = dict(players=np.array(players), cat=cs, match=ms, percat=cc, per_team=per_team)
    np.save('mwv.npy', out, allow_pickle=True)
    nm = names()
    for key in list(SEASONS) + ['2025-26-real']:
        d = out[key]
        order = np.argsort(-d['cat'])
        print(f'\n== {key}: top 25 by MWV (cat share, match share)')
        for i in order[:25]:
            print(f"  {nm[int(d['players'][i])]:<28} {d['cat'][i]:.3f}  {d['match'][i]:.3f}")
