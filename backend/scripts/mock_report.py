"""Ad-hoc reference (2026-10-03): team rosters + per-game team averages + simulated H2H ranking from a draft capture.

Usage: uv run python scripts/mock_report.py [league_id] [-v]   (default league: 2600009)
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.draft import capture
from app.draft.parser import parse_capture_line
from app.draft.state import replay

args = [a for a in sys.argv[1:] if not a.startswith('-')]
rows = list(capture.iter_rows(args[0] if args else '2600009'))
state = replay(te for te in map(parse_capture_line, rows) if te)
players = {str(p['id']): p for p in capture.v3_payload(rows, 'players')['player_list']}
teams = {t['id']: t['teamname'] for t in capture.v3_payload(rows, 'teams')['team_list']}
cats = {str(c['stat_id']): c['display_name'] for c in capture.v3_payload(rows, 'settings')['settings']['stat_categories']}
picks = {n: (p.player_id, p.team_id, p.price) for n, p in state.picks.items()}
if '-v' in sys.argv:
    print('stat ids:', cats); print('server budgets:', state.server_budgets); print('warnings:', state.warnings)

def name(pid): p = players[pid]; return f"{p['fname']} {p['lname']}"

# Table 1
print(f"## Tablo 1: Takımlar ({len(picks)} seçim)\n")
print("| Takım | Oyuncular (fiyat) | Harcanan | Kalan |\n|---|---|---|---|")
by_team = {t: [] for t in teams}
for n in sorted(picks):
    pid, tid, price = picks[n]; by_team[tid].append((pid, price))
for tid in sorted(by_team, key=lambda t: teams[t].lower()):
    lst = by_team[tid]; spent = sum(p for _, p in lst)
    s = ", ".join(f"{name(pid)} (${pr})" for pid, pr in lst) or "-"
    print(f"| {teams[tid]} | {s} | ${spent} | ${state.budget - spent} |")

# Table 2: per-game projections, team mean of players
COUNT = ['10', '12', '15', '16', '17', '18', '19']  # 3PTM PTS REB AST ST BLK TO
def pg(p, sid):
    ps = p['projected_stats']; gp = float(ps.get('0') or 0)
    return float(ps.get(sid) or 0) / gp if gp else 0.0
team_stats = {}
for tid, lst in by_team.items():
    if not lst: continue
    ps = [players[pid] for pid, _ in lst]
    s = {c: sum(pg(p, c) for p in ps) / len(ps) for c in COUNT}
    fgm = sum(pg(p, '4') for p in ps); fga = sum(pg(p, '3') for p in ps)
    ftm = sum(pg(p, '7') for p in ps); fta = sum(pg(p, '6') for p in ps)
    s['5'] = fgm / fga if fga else 0; s['8'] = ftm / fta if fta else 0
    s['0'] = sum(float(p['projected_stats'].get('0') or 0) for p in ps) / len(ps)
    team_stats[tid] = s
ORDER = ['5', '8', '10', '12', '15', '16', '17', '18', '19']
def h2h(a, b):
    w = l = t = 0
    for c in ORDER:
        x, y = team_stats[a][c], team_stats[b][c]
        if c == '19': x, y = -x, -y
        if abs(x - y) < 1e-9: t += 1
        elif x > y: w += 1
        else: l += 1
    return w, l, t
res = {}
for a in team_stats:
    W = L = T = mw = ml = 0
    for b in team_stats:
        if a == b: continue
        w, l, t = h2h(a, b)
        W += w; L += l; T += t
        mw += w > l; ml += w < l
    res[a] = (mw, ml, W, L, T)
n_cmp = len(team_stats)
print(f"\n{n_cmp} takım karşılaştırıldı, her takım {n_cmp-1} rakip. Oyuncusu olmayan takımlar en altta.")
print("\n## Tablo 2: Takım ortalamaları (oyuncu başı, maç başı projeksiyon) ve H2H sıralaması\n")
hdr = [cats.get(c, c) for c in ORDER]
print("| # | Takım | Oyuncu | Ort. GP | H2H maç G-M | Kategori G-M-B | " + " | ".join(hdr) + " |")
print("|" + "---|" * (6 + len(ORDER)))
rank = sorted(res, key=lambda t: (-res[t][0], -(res[t][2] - res[t][3])))
for i, tid in enumerate(rank, 1):
    mw, ml, W, L, T = res[tid]; s = team_stats[tid]
    vals = [f"{s[c]:.3f}" if c in ('5', '8') else f"{s[c]:.1f}" for c in ORDER]
    print(f"| {i} | {teams[tid]} | {len(by_team[tid])} | {s['0']:.0f} | {mw}-{ml} | {W}-{L}-{T} | " + " | ".join(vals) + " |")
for tid in sorted(teams):
    if tid not in team_stats:
        print(f"| - | {teams[tid]} | 0 | - | oyuncu yok | - | " + " | ".join("-" for _ in ORDER) + " |")
