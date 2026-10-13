"""Evidence check: exact one-player team-percentage impact (scaled by N*avg_att/((N-1)*avg_att+att)) vs the linear impact, both as z9 and G, vs MWV."""
import numpy as np
from vdata import *
from cands import raw_cats, PAPER_G
from app.analytics.valuation.core import PERCENT, basis_stats
out = np.load('mwv.npy', allow_pickle=True).item()
N = 12
for season in SEASONS:
    rows = season_totals(season); d = out[season]; mw = dict(zip(d['players'].tolist(), d['cat']))
    P, R = raw_cats(rows, 'totals')
    stats = {p: basis_stats(rows[p], 'totals') for p in P}
    # pool for averages: top 200 by plain z9 (one pass)
    Z = (R - R.mean(0)) / R.std(0); top = np.argsort(-Z.sum(1))[:200]
    Rs = R.copy()
    for j, (c, (m, a)) in enumerate(PERCENT.items()):
        att = np.array([stats[p][a] for p in P]); abar = att[top].mean()
        Rs[:, j] = R[:, j] * (N * abar / ((N - 1) * abar + att))
    def z_of(Rx):
        X = Rx[top]; return (Rx - X.mean(0)) / X.std(0)
    z_lin, z_sc = z_of(R), z_of(Rs)
    cands = {'z9 linear': z_lin.sum(1), 'z9 scaled': z_sc.sum(1), 'G linear': (z_lin * PAPER_G).sum(1), 'G scaled': (z_sc * PAPER_G).sum(1)}
    idx = {p: i for i, p in enumerate(P)}
    top200 = [p for p in sorted(mw, key=mw.get, reverse=True) if p in idx][:200]
    print(season, '  '.join(f"{k}={spearman([v[idx[p]] for p in top200], [mw[p] for p in top200]):.4f}" for k, v in cands.items()))
