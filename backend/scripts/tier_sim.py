"""Tier simulation (user, 2026-10-18): which mix of stars, value players and flyers builds the strongest
$200 team, judged by 9-cat H2H against a strong pool of real mock-draft teams.

Deterministic: fixed seed, no LLM. Reads the running backend (localhost:8000): the valuation of the Draft
tab's query and every followed mock draft. Writes a JSON result and an HTML report.

Usage: uv run python scripts/tier_sim.py [--draws 40] [--seed 7] [--out DIR]

Method
- Prices: every sold player's real mock sale prices. Each draw samples one price per player from the middle
  half of his own sales (realistic ranges). A pessimistic pass uses the 75th percentile of his sales ("I must outbid").
- Tiers (assumed thresholds, printed in the report):
  star   = average paid >= STAR_MIN and paid / our price <= STAR_MAX_RATIO (a small overpay is fine);
  value  = average paid in (FLYER_MAX, STAR_MIN) and paid / our price <= VALUE_MAX_RATIO;
  flyer  = average paid <= FLYER_MAX, plus players never sold in the mocks (cost $1).
  Players with an out-type Yahoo status are left out ("Q" stays: it is common before the season).
- Teams: for every cell (stars s, flyers f, value 12 - s - f) and every draw, every star combination is
  tried; the best f flyers by our price are added; the value slots are filled by a knapsack that maximizes
  our dollars under the money left, with a G G G F F F C slot assignment and total spend >= MIN_SPEND.
- Score: team line as in the app (frontend/src/lib/h2h.ts teamLine: counting totals / summed games, FG%
  and FT% = makes / attempts) against a fixed pool: the strongest non-autopick teams of the complete mocks.
"""
import argparse, itertools, json, os, random, statistics as st, sys, urllib.request
from collections import Counter, defaultdict

API = 'http://localhost:8000'
QUERY = dict(kind='projection', source='own', season='2026-27', basis='totals', model='gscore', dollars='savor', pool='144', punt='')
CATS = ['fg_pct', 'ft_pct', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
COUNT = ['tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
BUDGET, ROSTER, MIN_SPEND = 200, 12, 190
STAR_MIN, STAR_MAX_RATIO = 38, 1.5
FLYER_MAX, VALUE_MAX_RATIO = 4, 1.1
OUT_STATUS = {'O', 'INJ', 'OUT', 'IL', 'NA', 'SUSP'}
SLOTS = ['G', 'G', 'G', 'F', 'F', 'F', 'C']
STAR_COUNTS, FLYER_COUNTS = range(0, 4), range(0, 7)
POOL_SIZE = 11


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def team_line(players):
    ps = [p for p in players if (p['stats'].get('gp') or 0) > 0]
    s = lambda k: sum(p['stats'].get(k) or 0 for p in ps)
    games = s('gp')
    line = {k: s(k) / games for k in COUNT}
    line['fg_pct'] = s('fgm') / s('fga') if s('fga') else 0
    line['ft_pct'] = s('ftm') / s('fta') if s('fta') else 0
    return line


def cat_wins(a, b):
    w = 0.0
    for c in CATS:
        x, y = a[c], b[c]
        if abs(x - y) < 1e-9: w += 0.5
        elif (x < y) if c == 'tov' else (x > y): w += 1
    return w


def slots_ok(players):
    """G G G F F F C filled by distinct players (bipartite matching, small)."""
    match = {}
    def try_slot(i, seen):
        for j, p in enumerate(players):
            if SLOTS[i] in (p['positions'] or []) and j not in seen:
                seen.add(j)
                if j not in match or try_slot(match[j], seen):
                    match[j] = i
                    return True
        return False
    return all(try_slot(i, set()) for i in range(len(SLOTS)))


def load():
    val = get('/api/valuation?' + '&'.join(f'{k}={v}' for k, v in QUERY.items()))
    by_id = {p['player_id']: p for p in val['players']}
    sales, boards = defaultdict(list), {}
    for d in get('/api/draft/live'):
        if not d['picks']: continue
        b = get(f"/api/draft/live/{d['league_id']}/board")
        boards[d['league_id']] = b
        for pk in b['picks']:
            if pk['player_pk'] in by_id: sales[pk['player_pk']].append(pk['price'])
    return val, by_id, sales, boards


def tiers(val, sales):
    star, value, flyer, out = [], [], [], []
    for p in val['players']:
        ours = p['dollars'] or 0
        if (p.get('injury') or '') in OUT_STATUS:
            if p['player_id'] in sales: out.append((p, 'out status ' + p['injury']))
            continue
        xs = sales.get(p['player_id'])
        if not xs:
            if ours >= 2: flyer.append(dict(p=p, prices=[1], avg=1.0))  # never sold in a mock: a $1 player
            continue
        avg = st.mean(xs)
        e = dict(p=p, prices=xs, avg=avg, ratio=avg / max(ours, 0.5))
        if avg >= STAR_MIN:
            (star if e['ratio'] <= STAR_MAX_RATIO else out).append(e if e['ratio'] <= STAR_MAX_RATIO else (p, f'star overpay {e["ratio"]:.2f}x'))
        elif avg > FLYER_MAX:
            (value if e['ratio'] <= VALUE_MAX_RATIO else out).append(e if e['ratio'] <= VALUE_MAX_RATIO else (p, f'value overpay {e["ratio"]:.2f}x'))
        elif ours > 0:
            flyer.append(e)
    return star, value, flyer, out


def opponent_pool(boards, by_id):
    """Strongest non-autopick teams of the complete mocks (12 best players each, by our price)."""
    teams = []
    for lid, b in boards.items():
        if len(b['picks']) < 12 * len(b['teams']): continue
        auto = {t['team_id'] for t in b['teams'] if t['autopick']}
        names = {t['team_id']: t['name'] for t in b['teams']}
        roster = defaultdict(list)
        for pk in b['picks']:
            if pk['player_pk'] in by_id: roster[pk['team_id']].append((by_id[pk['player_pk']], pk['price']))
        for tid, ps in roster.items():
            top = sorted(ps, key=lambda x: -(x[0]['dollars'] or 0))[:ROSTER]
            teams.append(dict(draft=lid, team=names.get(tid), auto=tid in auto, paid=sum(pr for _, pr in ps),
              value=sum(p['dollars'] or 0 for p, _ in top), players=[p['name'] for p, _ in top], line=team_line([p for p, _ in top])))
    for t in teams:
        t['rr'] = st.mean(cat_wins(t['line'], u['line']) / 9 for u in teams if u is not t)
    human = sorted((t for t in teams if not t['auto']), key=lambda t: -t['rr'])
    return human[:POOL_SIZE], teams


def knapsack(items, k, budget, min_spend):
    """Best `k` items by value with integer cost in [min_spend, budget]. Returns candidate sets, best first."""
    NEG = float('-inf')
    best = [[NEG] * (budget + 1) for _ in range(k + 1)]
    take = [[None] * (budget + 1) for _ in range(k + 1)]
    best[0][0] = 0.0
    take[0][0] = ()
    for i, (cost, v, _) in enumerate(items):
        for n in range(k - 1, -1, -1):
            row, nxt = best[n], best[n + 1]
            for b in range(budget - cost, -1, -1):
                if row[b] == NEG: continue
                if row[b] + v > nxt[b + cost]:
                    nxt[b + cost] = row[b] + v
                    take[n + 1][b + cost] = take[n][b] + (i,)
    ends = sorted((b for b in range(max(min_spend, 0), budget + 1) if best[k][b] > NEG), key=lambda b: -best[k][b])
    return [take[k][b] for b in ends]


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def middle_draw(xs, rnd):
    """One of his sale prices from the middle half (25th to 75th percentile). The full range lets the optimizer
    pick every player at his single cheapest sale, which no real draft gives."""
    xs = sorted(xs)
    lo, hi = int(0.25 * len(xs)), max(int(0.25 * len(xs)), min(len(xs) - 1, int(0.75 * len(xs))))
    return rnd.choice(xs[lo:hi + 1])


def simulate(star, value, flyer, pool, draws, seed, price_mode):
    rnd = random.Random(seed)
    results = []
    for d in range(draws):
        price = lambda e: quantile(e['prices'], 0.75) if price_mode == 'p75' else middle_draw(e['prices'], rnd)
        sp = [(max(1, price(e)), e) for e in star]
        vp = [(max(1, price(e)), e) for e in value]
        fp = sorted(((max(1, price(e)), e) for e in flyer), key=lambda x: -(x[1]['p']['dollars'] or 0))
        v_items = [(c, e['p']['dollars'] or 0, e) for c, e in vp]
        for s in STAR_COUNTS:
            for combo in itertools.combinations(sp, s):
                s_cost = sum(c for c, _ in combo)
                if s_cost > BUDGET: continue
                for f in FLYER_COUNTS:
                    v = ROSTER - s - f
                    if v < 0: continue
                    fl = [x for x in fp if x[0] <= FLYER_MAX][:f]
                    if len(fl) < f: continue
                    f_cost = sum(c for c, _ in fl)
                    left = BUDGET - s_cost - f_cost
                    if left < v: continue
                    fixed = [e['p'] for _, e in combo] + [e['p'] for _, e in fl]
                    for pick in knapsack(v_items, v, left, MIN_SPEND - s_cost - f_cost)[:6]:
                        team = fixed + [v_items[i][2]['p'] for i in pick]
                        if not slots_ok(team): continue
                        cost = s_cost + f_cost + sum(v_items[i][0] for i in pick)
                        line = team_line(team)
                        w = [cat_wins(line, o['line']) for o in pool]
                        results.append(dict(s=s, v=v, f=f, draw=d, cost=cost,
                          value=round(sum(p['dollars'] or 0 for p in team), 1), cat=sum(w) / (9 * len(pool)),
                          wl=[sum(x > 4.5 for x in w), sum(x < 4.5 for x in w)],
                          players=[[p['name'], p['nba_id'], tier_of[p['player_id']], price_of(p, combo, fl, vp)] for p in team],
                          line=line))
                        break
    return results


tier_of = {}


def price_of(p, combo, fl, vp):
    for c, e in list(combo) + list(fl) + list(vp):
        if e['p']['player_id'] == p['player_id']: return c
    return None


def summarize(results):
    cells = defaultdict(list)
    for r in results: cells[(r['s'], r['f'])].append(r)
    out = []
    for (s, f), rs in sorted(cells.items()):
        cats = sorted(r['cat'] for r in rs)
        q = lambda x: cats[min(len(cats) - 1, int(x * len(cats)))]
        # Best team per price draw: what a manager who picks the best star combination would get.
        per_draw = defaultdict(float)
        for r in rs: per_draw[r['draw']] = max(per_draw[r['draw']], r['cat'])
        out.append(dict(s=s, f=f, v=ROSTER - s - f, n=len(rs), median=q(0.5), p25=q(0.25), p75=q(0.75), best=cats[-1],
          smart=st.median(per_draw.values()),
          wins=st.median(r['wl'][0] for r in rs), cost=st.median(r['cost'] for r in rs), value=st.median(r['value'] for r in rs)))
    return out


def headshots(ids, cache):
    """NBA.com headshots as data URIs (an artifact page cannot load outside images). Cached on disk; curl, since
    Python's urllib fails the CDN's TLS here."""
    import base64, subprocess
    os.makedirs(cache, exist_ok=True)
    out = {}
    for i in sorted(ids):
        f = os.path.join(cache, f'{i}.png')
        if not os.path.exists(f):
            subprocess.run(['curl', '-sSf', '-o', f, f'https://cdn.nba.com/headshots/nba/latest/260x190/{i}.png'], capture_output=True)
        if os.path.exists(f) and os.path.getsize(f):
            out[i] = 'data:image/png;base64,' + base64.b64encode(open(f, 'rb').read()).decode()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--draws', type=int, default=40)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'tier_sim'))
    a = ap.parse_args()
    val, by_id, sales, boards = load()
    star, value, flyer, out = tiers(val, sales)
    for name, xs in (('star', star), ('value', value), ('flyer', flyer)):
        for e in xs: tier_of[e['p']['player_id']] = name
    pool, all_teams = opponent_pool(boards, by_id)
    print(f'tiers: {len(star)} stars, {len(value)} value, {len(flyer)} flyers; pool {len(pool)} of {len(all_teams)} mock teams', file=sys.stderr)
    res = simulate(star, value, flyer, pool, a.draws, a.seed, 'sample')
    pess = simulate(star, value, flyer, pool, 1, a.seed, 'p75')
    print(f'teams: {len(res)} sampled, {len(pess)} at p75', file=sys.stderr)

    seen, top = set(), []
    for r in sorted(res, key=lambda r: -r['cat']):
        key = tuple(sorted(p[0] for p in r['players']))
        if key not in seen: seen.add(key); top.append(r)
    decile = top[:max(1, len(top) // 10)]
    freq = Counter(p[0] for r in decile for p in r['players'])
    info = {e['p']['name']: e for e in star + value + flyer}
    pairs = defaultdict(list)
    for r in res:
        if r['s']: pairs[' + '.join(sorted(p[0] for p in r['players'] if p[2] == 'star'))].append(r['cat'])
    tier_rows = lambda xs, t: [dict(name=e['p']['name'], nba=e['p']['nba_id'], tier=t, avg=round(e['avg'], 1), n=len(e['prices']),
      lo=min(e['prices']), hi=max(e['prices']), ours=round(e['p']['dollars'] or 0, 1), pos=e['p']['positions'], injury=e['p'].get('injury'))
      for e in sorted(xs, key=lambda e: -e['avg'])]
    report = dict(
      generated=__import__('datetime').date.today().isoformat(), seed=a.seed, draws=a.draws, query=QUERY,
      rules=dict(budget=BUDGET, roster=ROSTER, min_spend=MIN_SPEND, star_min=STAR_MIN, star_max_ratio=STAR_MAX_RATIO,
        flyer_max=FLYER_MAX, value_max_ratio=VALUE_MAX_RATIO, pool_size=POOL_SIZE),
      drafts=len(boards), sales=sum(len(x) for x in sales.values()),
      tiers=tier_rows(star, 'star') + tier_rows(value, 'value') + tier_rows(flyer, 'flyer'),
      excluded=[dict(name=(x[0] if isinstance(x, tuple) else x['p'])['name'], why=x[1] if isinstance(x, tuple) else '') for x in out],
      pool=[dict(draft=t['draft'], team=t['team'], paid=t['paid'], value=round(t['value']), rr=round(t['rr'], 3), players=t['players']) for t in pool],
      cells=summarize(res), cells_p75=summarize(pess), teams=len(res), unique_teams=len(top),
      top=[{k: v for k, v in r.items() if k != 'line'} for r in top[:30]],
      freq=[dict(name=n, count=c, share=round(c / len(decile), 3), tier=tier_of.get(info[n]['p']['player_id']) if n in info else None,
        avg=round(info[n]['avg'], 1) if n in info else None, ours=round(info[n]['p']['dollars'] or 0, 1) if n in info else None,
        nba=info[n]['p']['nba_id'] if n in info else None) for n, c in freq.most_common(40)],
      pairs=sorted((dict(stars=k, n=len(v), median=st.median(v), best=max(v)) for k, v in pairs.items() if len(v) >= 5),
        key=lambda x: -x['median'])[:30],
    )
    os.makedirs(a.out, exist_ok=True)
    report['heads'] = headshots({x['nba'] for x in report['tiers'] if x['nba']}, os.path.join(a.out, 'heads'))
    path = os.path.join(a.out, 'tier_sim.json')
    json.dump(report, open(path, 'w'), indent=1)
    # HTML report: the template in this folder with the JSON inlined (photos load from the NBA CDN).
    tpl = open(os.path.join(os.path.dirname(__file__), 'tier_sim_report.html')).read()
    html = tpl.replace('__DATA__', json.dumps(report, separators=(',', ':')))
    open(os.path.join(a.out, 'tier_sim.html'), 'w').write(html)
    print(path)


if __name__ == '__main__':
    main()
