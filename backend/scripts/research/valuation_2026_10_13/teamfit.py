"""Which players would have helped each real 2025-26 roster the most (marginal cat share when added to the roster minus one member)."""
import sqlite3
import numpy as np
from vdata import *

out = np.load('mwv.npy', allow_pickle=True).item()['2025-26-real']
nm = names()
players = out['players'].tolist()
con = sqlite3.connect(DB)
did = con.execute("select id from drafts where kind='past_league' and season='2025-26'").fetchone()[0]
tn = {}
for r in con.execute("select * from draft_teams where draft_pk=?", (did,)):
    tn[r[2]] = r[3] if len(r) > 3 else str(r[2])
picks = past_draft('2025-26')
own = {}
for pk, t, pr in picks:
    own.setdefault(t, set()).add(pk)
for t, vals in sorted(out['per_team'].items()):
    order = np.argsort(-vals)
    free = [i for i in order if players[i] not in own[t]][:6]
    mine = sorted([i for i in order if players[i] in own[t]], key=lambda i: -vals[i])
    print(f'team {t} ({tn.get(t, "?")}): best adds: ' + ', '.join(f'{nm[players[i]]} {vals[i]:.3f}' for i in free))
    print('    own best 3: ' + ', '.join(f'{nm[players[i]]} {vals[i]:.3f}' for i in mine[:3]) + ' | own worst 2: ' + ', '.join(f'{nm[players[i]]} {vals[i]:.3f}' for i in mine[-2:]))
