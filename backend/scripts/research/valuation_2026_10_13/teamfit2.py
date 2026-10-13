"""Team-conditional value demo on real 2025-26 rosters: for 3 teams, the best free adds by simulation vs by G-score,
and each own member's marginal (full roster minus roster without him)."""
import sqlite3
import numpy as np
from vdata import *
from cands import candidates
from mwv import score_candidates, cat_lines

season = '2025-26'
players, weeks, W, G = weekly(season)
idx = {p: i for i, p in enumerate(players)}
nm = names(); tot = season_totals(season)
picks = past_draft(season)
con = sqlite3.connect(DB)
did = con.execute("select id from drafts where kind='past_league' and season=?", (season,)).fetchone()[0]
tn = dict(con.execute("select team_id, name from draft_teams where draft_pk=?", (did,)))
rosters = {}
for pk, t, pr in picks:
    if pk in idx: rosters.setdefault(t, []).append(idx[pk])
gs = candidates(tot, 'totals', 200)['gscore (paper w)']
teams = sorted(rosters)


def team_score(roster, opps):
    X = cat_lines(W[np.array(roster)].sum(0)); O = cat_lines(np.stack([W[o].sum(0) for o in opps]))
    win = (X[None] > O).astype(float) + 0.5 * (X[None] == O)
    return win.mean()


for t in (6, 8, 12):
    opps = [np.array(rosters[o]) for o in teams if o != t]
    full = team_score(rosters[t], opps)
    print(f'\nteam {t} ({tn.get(t)}): cat share with the draft roster {full:.3f}')
    # own members: marginal = full - without him
    marg = sorted(((full - team_score([x for x in rosters[t] if x != m], opps), m) for m in rosters[t]), reverse=True)
    print('  own members, marginal cat share: ' + ', '.join(f'{nm[players[m]]} {v:+.3f}' for v, m in marg))
    # free adds: replace the weakest member (lowest marginal) with each candidate
    weakest = marg[-1][1]
    base = np.array([x for x in rosters[t] if x != weakest])
    cs, ms, cc = score_candidates(W, base, opps)
    own = set(rosters[t])
    order = [i for i in np.argsort(-cs) if i not in own][:8]
    print(f'  best adds in place of {nm[players[weakest]]} (sim): ' + ', '.join(f'{nm[players[i]]} {cs[i] - full:+.3f}' for i in order))
    by_g = sorted((p for p in gs if p in idx and idx[p] not in own), key=gs.get, reverse=True)[:8]
    print('  best adds by G-score: ' + ', '.join(f'{nm[p]} {cs[idx[p]] - full:+.3f}' for p in by_g))
