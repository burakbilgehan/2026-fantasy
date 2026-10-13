"""Step 4: empirical category weights. OLS of MWV on the 9 category z (totals, pool 200), per season and cross-validated."""
import numpy as np
from vdata import *
from cands import zmat, PAPER_G

out = np.load('mwv.npy', allow_pickle=True).item()
data = {}
for season in SEASONS:
    rows = season_totals(season)
    P, Z = zmat(rows, 'totals', 200)
    d = out[season]; mw = dict(zip(d['players'].tolist(), d['cat']))
    top = [p for p in sorted(mw, key=mw.get, reverse=True) if p in rows and rows[p]['gp'] > 0][:250]
    idx = {p: i for i, p in enumerate(P)}
    X = np.array([Z[idx[p]] for p in top]); y = np.array([mw[p] for p in top])
    data[season] = (X, y, top, P, Z, mw)


def fit(X, y):
    A = np.hstack([X, np.ones((len(X), 1))])
    w, *_ = np.linalg.lstsq(A, y, rcond=None)
    return w[:9]


print('OLS weights per season (scaled so the mean weight is 1), sample = top 250 by MWV:')
print('%-8s ' % 'season' + ' '.join('%6s' % c[:6] for c in CATS))
W = {}
for s, (X, y, *_) in data.items():
    w = fit(X, y); w = w / w.mean(); W[s] = w
    print('%-8s ' % s[2:] + ' '.join('%6.2f' % v for v in w))
wall = np.mean([W[s] for s in SEASONS], 0)
print('%-8s ' % 'mean' + ' '.join('%6.2f' % v for v in wall))
print('%-8s ' % 'paper G' + ' '.join('%6.2f' % v for v in PAPER_G / PAPER_G.mean()))

print('\nLeave-one-season-out: weights fit on the other 3 seasons, Spearman vs MWV on the held-out season (top 200 by MWV):')
for s in SEASONS:
    Xs = np.vstack([data[t][0] for t in SEASONS if t != s]); ys = np.concatenate([data[t][1] for t in SEASONS if t != s])
    w = fit(Xs, ys)
    X, y, top, P, Z, mw = data[s]
    top200 = top[:200]
    idx = {p: i for i, p in enumerate(top)}
    pred = X[:200] @ w
    r_fit = spearman(pred, y[:200])
    r_g = spearman(X[:200] @ PAPER_G, y[:200])
    r_z = spearman(X[:200].sum(1), y[:200])
    print('  held out %s: fitted %.3f   G-score %.3f   z9 %.3f' % (s, r_fit, r_g, r_z))

# a per-category view: how much of MWV each category explains (univariate rho of z_c with MWV)
print('\nUnivariate Spearman of each category z with MWV (top 250), per season:')
print('%-8s ' % 'season' + ' '.join('%6s' % c[:6] for c in CATS))
for s, (X, y, *_) in data.items():
    print('%-8s ' % s[2:] + ' '.join('%6.2f' % spearman(X[:, i], y) for i in range(9)))
