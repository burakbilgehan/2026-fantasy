"""Step 3: hindsight snake-draft tournament. 12 teams, each drafts by one candidate's ranking (totals basis,
real season totals). Random draft order, 12 rounds, best available by own list. Then all-play weekly H2H.
Repeated draws; mean category and matchup win share per candidate. Usage: python3 tournament.py [draws]"""
import sys
import numpy as np
from vdata import *
from cands import candidates
from mwv import cat_lines

DRAWS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
PICK = ['z9', 'minus1', 'minus2', 'durant_approx (8cat minus1)', 'gscore (paper w)', 'g minus1', 'punt TO',
        'robust z9 (median/MAD)', 'tanh z9 s=2.5', 'sqrt-skew z8 minus1', 'sqrt-skew tanh z8 s=2 minus1', 'fantasy pts (yahoo)']
out = np.load('mwv.npy', allow_pickle=True).item()


def all_play(W, rosters):
    L = cat_lines(np.stack([W[r].sum(0) for r in rosters]))  # (T, nw, 9)
    win = (L[:, None] > L[None]).astype(np.float32) + 0.5 * (L[:, None] == L[None])  # (T, T, nw, 9)
    T = len(rosters)
    mask = ~np.eye(T, dtype=bool)
    cats = win.sum(-1)  # (T, T, nw)
    match = (cats > 4.5) + 0.5 * (cats == 4.5)
    return win[mask].reshape(T, T - 1, -1, 9).mean(axis=(1, 2, 3)), match[mask].reshape(T, T - 1, -1).mean(axis=(1, 2))


def season_tournament(season, draws, with_mwv):
    players, weeks, W, G = weekly(season)
    idx = {p: i for i, p in enumerate(players)}
    rows = season_totals(season)
    cands = candidates(rows, 'totals', 200)
    names_ = list(PICK)
    if with_mwv:
        d = out[season]; cands['MWV (hindsight oracle)'] = dict(zip(d['players'].tolist(), d['cat'])); names_.append('MWV (hindsight oracle)')
    lists = {n: [idx[p] for p in sorted(cands[n], key=cands[n].get, reverse=True) if p in idx] for n in names_}
    rng = np.random.default_rng(7)
    acc = {n: [] for n in names_}; accm = {n: [] for n in names_}
    for _ in range(draws):
        teams = list(rng.permutation(names_))[:12] if len(names_) >= 12 else list(names_)
        while len(teams) < 12:
            teams.append(teams[rng.integers(len(teams))])
        order = rng.permutation(12)
        taken = set(); rosters = [[] for _ in range(12)]; ptr = {n: 0 for n in names_}
        for rnd in range(12):
            seq = order if rnd % 2 == 0 else order[::-1]
            for t in seq:
                lst = lists[teams[t]]
                while lst[ptr[teams[t]]] in taken:
                    ptr[teams[t]] += 1
                p = lst[ptr[teams[t]]]; taken.add(p); rosters[t].append(p)
            # a candidate used by two teams shares a pointer: reset pointers each round
            for n in names_: ptr[n] = 0
        cs, ms = all_play(W, [np.array(r) for r in rosters])
        for t, n in enumerate(teams):
            acc[n].append(cs[t]); accm[n].append(ms[t])
    return {n: (np.mean(acc[n]), np.std(acc[n]) / np.sqrt(len(acc[n])), np.mean(accm[n]), len(acc[n])) for n in names_}


if __name__ == '__main__':
    with_mwv = '--oracle' in sys.argv
    res = {s: season_tournament(s, DRAWS, with_mwv) for s in SEASONS}
    names_ = list(res[SEASONS[0]])
    print('Hindsight snake tournament, %d draws per season. cat share (se) | match share. Mean over 4 seasons at the right.' % DRAWS)
    print('%-32s ' % 'model' + ' '.join('%17s' % s for s in SEASONS) + '   mean cat  mean match')
    rows_ = sorted(names_, key=lambda n: -np.mean([res[s][n][0] for s in SEASONS]))
    for n in rows_:
        cells = ' '.join('%.3f(%.3f) %.3f' % (res[s][n][0], res[s][n][1], res[s][n][2]) for s in SEASONS)
        print('%-32s %s   %.3f     %.3f' % (n, cells, np.mean([res[s][n][0] for s in SEASONS]), np.mean([res[s][n][2] for s in SEASONS])))
