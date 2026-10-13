"""Step 1: does our straight 9-cat z-score reproduce the 'straight 9-cat' ranks Lloyd quotes for 2025-26?"""
import numpy as np
from vdata import *
from app.analytics.valuation import Settings, run

nm = names()
tot = season_totals('2025-26')
print('players with 2025-26 totals:', len(tot), ' gp>0:', sum(1 for r in tot.values() if r['gp'] > 0))
variants = {
    'tot/all': Settings(basis='totals', pool=None), 'tot/200': Settings(basis='totals', pool=200),
    'pg/all': Settings(basis='per_game', pool=None), 'pg/200': Settings(basis='per_game', pool=200),
}
# per game with a GP floor (Lloyd's per-game lists presumably skip tiny samples)
ranks = {}
for k, s in variants.items():
    res = run(tot, 'zscore', s)
    ranks[k] = {p: r['rank'] for p, r in res.items()}
for floor in (20, 30, 41):
    sub = {p: r for p, r in tot.items() if r['gp'] >= floor}
    res = run(sub, 'zscore', Settings(basis='per_game', pool=None))
    ranks[f'pg/all/gp{floor}'] = {p: r['rank'] for p, r in res.items()}

print('\n%-24s %5s %5s | %s' % ('player', 'L-S', 'L-D', ' '.join('%10s' % k for k in ranks)))
pk_of = {}
for name in sorted(set(LLOYD_S) | set(LLOYD_D), key=lambda n: LLOYD_D.get(n, 999)):
    pk = find_player(name, nm)
    pk_of[name] = pk
    if pk is None:
        print('%-24s UNMATCHED' % name); continue
    gp = tot.get(pk, {}).get('gp', 0)
    print('%-24s %5s %5s | %s   gp=%d' % (name[:24], LLOYD_S.get(name, ''), LLOYD_D.get(name, ''),
          ' '.join('%10s' % ranks[k].get(pk, '-') for k in ranks), gp))

print('\nSpearman of our rank vs Lloyd S (straight 9-cat) and vs Lloyd D (DURANT):')
for k in ranks:
    for label, L in (('S', LLOYD_S), ('D', LLOYD_D)):
        pairs = [(L[n], ranks[k][pk_of[n]]) for n in L if pk_of.get(n) and pk_of[n] in ranks[k]]
        print('  %-14s vs %s: rho=%.3f  n=%d' % (k, label, spearman([a for a, _ in pairs], [b for _, b in pairs]), len(pairs)))
