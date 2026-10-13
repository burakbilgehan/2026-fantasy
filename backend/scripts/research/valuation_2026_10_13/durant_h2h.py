"""DURANT H2H as published (joshlloydfantasy.com/research/durant-fantasy-basketball, read 2026-10-13):
Yeo-Johnson per category (MLE lambda), standardise, weights PTS 1.00 REB 0.94 AST 0.75 others 0.60, TO excluded, Minus 1
(worst of the 8 removed). Per game, full NBA sample. Broad DURANT: all 1.00, TO 0.50, no Minus 1. Test vs Lloyd's quotes;
plus Hashtag's -2 floor and the DURANT H2H formula on the totals basis vs MWV."""
import numpy as np
from app.analytics.valuation.transform import fit_lambda, yeo_johnson
from vdata import *
from cands import raw_cats, candidates

W_H2H = np.array([0.60, 0.60, 0.60, 1.00, 0.94, 0.75, 0.60, 0.60])  # fg ft tpm pts reb ast stl blk
nm = names()
tot = season_totals('2025-26')
pk_of = {n: find_player(n, nm) for n in set(LLOYD_D) | set(LLOYD_S)}


def yj_z(R):
    Z = np.zeros_like(R)
    for j in range(R.shape[1]):
        x = R[:, j].copy()
        if j == 8: x = -x  # raw turnovers, positive and skewed
        y = np.array(yeo_johnson(list(x), fit_lambda(list(x))))
        z = (y - y.mean()) / y.std()
        Z[:, j] = -z if j == 8 else z
    return Z


def durant(rows, basis='per_game', min_gp=1, h2h=True, minus1_on='weighted'):
    sub = {p: r for p, r in rows.items() if r['gp'] >= min_gp}
    P, R = raw_cats(sub, basis)
    Z = yj_z(R)
    if h2h:
        C = Z[:, :8] * W_H2H
        if minus1_on == 'weighted':
            total = C.sum(1) - C.min(1)
        else:
            worst = Z[:, :8].argmin(1)
            total = C.sum(1) - C[np.arange(len(P)), worst]
    else:
        total = Z[:, :8].sum(1) + 0.5 * Z[:, 8]
    return dict(zip(P, total))


def report(name, vals):
    order = sorted(vals, key=vals.get, reverse=True); rank = {p: i + 1 for i, p in enumerate(order)}
    pairs = [(LLOYD_D[n], rank[pk_of[n]]) for n in LLOYD_D if pk_of[n] in rank]
    pairsS = [(LLOYD_S[n], rank[pk_of[n]]) for n in LLOYD_S if pk_of[n] in rank]
    mad = np.mean([abs(np.log(a) - np.log(b)) for a, b in pairs])
    print('%-44s vs D rho=%.3f  mean|log err|=%.2f  n=%d | vs S rho=%.3f' % (name, spearman(*zip(*pairs)), mad, len(pairs), spearman(*zip(*pairsS))))
    return rank


r1 = report('DURANT H2H (article), pg, all players', durant(tot))
r2 = report('DURANT H2H, minus1 on raw z', durant(tot, minus1_on='raw'))
r3 = report('DURANT H2H, gp>=10', durant(tot, min_gp=10))
r4 = report('DURANT H2H, gp>=20', durant(tot, min_gp=20))
r5 = report('DURANT broad (TO 0.5, no minus1), pg', durant(tot, h2h=False))
r6 = report('DURANT H2H without Yeo-Johnson (plain z)', None) if False else None
# ablations: no transform; no weights
def ablate(transform=True, weights=True):
    P, R = raw_cats(tot, 'per_game')
    Z = yj_z(R) if transform else (R - R.mean(0)) / R.std(0)
    C = Z[:, :8] * (W_H2H if weights else 1.0)
    return dict(zip(P, C.sum(1) - C.min(1)))
report('ablation: weights, no transform', ablate(transform=False))
report('ablation: transform, no weights', ablate(weights=False))
report('ablation: neither (= current approx.)', ablate(False, False))
print('\nKey names: Lloyd D | DURANT H2H article | gp>=10 | broad')
for n in ['Giannis Antetokounmpo', 'Jaylen Brown', 'Paolo Banchero', 'Stephon Castle', 'Pascal Siakam', 'Alperen Sengun', 'Chet Holmgren',
          'Jay Huff', 'Payton Pritchard', "Kel'el Ware", 'Walker Kessler', 'Onyeka Okongwu', 'Rudy Gobert', 'Jaden McDaniels', 'Stephen Curry', 'Tyrese Maxey', 'Kevin Durant']:
    pk = pk_of[n]
    print('  %-24s %4d | %4s | %4s | %4s' % (n, LLOYD_D[n], r1.get(pk, '-'), r3.get(pk, '-'), r5.get(pk, '-')))

# totals basis vs MWV, 4 seasons, plus Hashtag floor -2
out = np.load('mwv.npy', allow_pickle=True).item()
print('\nTotals basis, Spearman vs MWV (top 200): DURANT H2H formula, Hashtag floor -2 z9, Hashtag H2H default (floor -2, TO x0.25)')
for season in SEASONS:
    rows = season_totals(season); d = out[season]; mw = dict(zip(d['players'].tolist(), d['cat']))
    dh = durant(rows, basis='totals')
    P, R = raw_cats(rows, 'totals'); Z = (R - R.mean(0)) / R.std(0)
    fl = dict(zip(P, np.maximum(Z, -2).sum(1)))
    Zh = Z.copy(); Zh[:, 8] *= 0.25
    flh = dict(zip(P, np.maximum(Zh, -2).sum(1)))
    top = [p for p in sorted(mw, key=mw.get, reverse=True) if p in dh][:200]
    print('  %s: DURANT H2H %.3f | floor-2 z9 %.3f | Hashtag H2H default %.3f' % (season,
          spearman([dh[p] for p in top], [mw[p] for p in top]), spearman([fl[p] for p in top], [mw[p] for p in top]), spearman([flh[p] for p in top], [mw[p] for p in top])))
