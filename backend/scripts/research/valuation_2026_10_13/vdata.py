"""Data loader for the valuation research (throwaway). Reads data/fantasy.db directly."""
import sqlite3, sys, unicodedata
from collections import defaultdict
from datetime import date, timedelta
import numpy as np

ROOT = str(__import__('pathlib').Path(__file__).resolve().parents[4])  # repo root
DB = ROOT + '/data/fantasy.db'
sys.path.insert(0, ROOT + '/backend')  # the project's valuation code

STATS = ['fgm', 'fga', 'ftm', 'fta', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
CATS = ['fg_pct', 'ft_pct', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
SEASONS = ['2022-23', '2023-24', '2024-25', '2025-26']


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.lower().replace('.', '').replace("'", '').replace('-', ' ').strip()


def last_sunday_of_march(end_year):
    d = date(end_year, 3, 31)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def connect():
    return sqlite3.connect(DB)


def names():
    con = connect()
    out = {pk: f"{f} {l}" for pk, f, l in con.execute("select id, first_name, last_name from players")}
    con.close()
    return out


def find_player(name, name_map=None):
    """Match a quoted name to a player pk (full name, else last name + first-name prefix)."""
    name_map = name_map or names()
    n = norm(name)
    by_norm = {norm(v): k for k, v in name_map.items()}
    if n in by_norm:
        return by_norm[n]
    parts = n.split()
    cands = [k for k, v in name_map.items() if norm(v).split()[-1] == parts[-1] or (len(parts) > 1 and parts[-1] in norm(v).split())]
    if len(parts) > 1:
        cands2 = [k for k in cands if norm(name_map[k]).startswith(parts[0][:3])]
        if len(cands2) == 1:
            return cands2[0]
    if len(cands) == 1:
        return cands[0]
    return None


def season_totals(season, source='nba'):
    """pk -> row dict with gp, min and the 11 stats (season totals)."""
    con = connect()
    cols = ['gp', 'min'] + STATS
    rows = {}
    for r in con.execute(f"select player_pk, {', '.join(cols)} from player_season_stats where source=? and season=?", (source, season)):
        rows[r[0]] = {c: float(v or 0) for c, v in zip(cols, r[1:])}
    con.close()
    return rows


def projection(season, source):
    con = connect()
    cols = ['gp', 'min'] + STATS
    rows = {}
    for r in con.execute(f"select player_pk, {', '.join(cols)} from player_projections where source=? and season=?", (source, season)):
        rows[r[0]] = {c: float(v or 0) for c, v in zip(cols, r[1:])}
    con.close()
    return rows


def weekly(season):
    """Weekly box-score sums per player for the fantasy season (Mon-Sun weeks up to the last Sunday of March).

    Returns players (list of pk), weeks (list of Mondays), W array (P, nweeks, 11), gp_week (P, nweeks).
    """
    end_year = int(season[:4]) + 1
    last = last_sunday_of_march(end_year)
    con = connect()
    acc = defaultdict(lambda: defaultdict(lambda: np.zeros(11)))
    gcount = defaultdict(lambda: defaultdict(int))
    for r in con.execute(f"select player_pk, game_date, {', '.join(STATS)} from player_game_logs where season=? and season_type='regular'", (season,)):
        d = date.fromisoformat(r[1][:10])
        if d > last:
            continue
        monday = d - timedelta(days=d.weekday())
        acc[r[0]][monday] += np.array([float(v or 0) for v in r[2:]])
        gcount[r[0]][monday] += 1
    con.close()
    weeks = sorted({w for p in acc.values() for w in p})
    players = sorted(acc)
    widx = {w: i for i, w in enumerate(weeks)}
    W = np.zeros((len(players), len(weeks), 11))
    G = np.zeros((len(players), len(weeks)))
    for i, p in enumerate(players):
        for w, v in acc[p].items():
            W[i, widx[w]] = v
            G[i, widx[w]] = gcount[p][w]
    return players, weeks, W, G


def past_draft(season='2025-26'):
    """2025-26 league auction: list of (pk, team_id, price)."""
    con = connect()
    yahoo = dict(con.execute("select external_id, player_pk from player_external_ids where source='yahoo'"))
    did = con.execute("select id from drafts where kind='past_league' and season=?", (season,)).fetchone()[0]
    picks = [(yahoo.get(str(y)), t, int(pr)) for y, t, pr in con.execute("select yahoo_player_id, team_id, price from draft_picks where draft_pk=?", (did,))]
    con.close()
    return picks


def spearman(x, y):
    """Spearman rank correlation (average ranks for ties), numpy only."""
    def ranks(v):
        v = np.asarray(v, dtype=float)
        order = np.argsort(v, kind='mergesort'); r = np.empty(len(v)); r[order] = np.arange(1, len(v) + 1)
        for val in np.unique(v):
            m = v == val
            if m.sum() > 1:
                r[m] = r[m].mean()
        return r
    a, b = ranks(x), ranks(y)
    return float(np.corrcoef(a, b)[0, 1])


# Lloyd's quoted ranks for 2025-26 ("last season"), from docs/knowledge/claims.md.
# S = "straight 9-cat" rank he quotes to mock it; D = his DURANT (he says "categories", "Durant", "head-to-head").
LLOYD_S = {
    'Giannis Antetokounmpo': 70, 'Paolo Banchero': 129, 'Stephon Castle': 169, 'Jalen Brunson': 50,
    'Andrew Wiggins': 60, 'Trey Murphy': 11, 'Walker Kessler': 11, 'Kevin Durant': 9, 'Cooper Flagg': 36,
    'Jaylen Brown': 70, "Kel'el Ware": 30,
}
LLOYD_D = {
    'Deni Avdija': 35, "Kel'el Ware": 95, 'Kevin Durant': 14, 'Paolo Banchero': 56, 'Ty Jerome': 47,
    'Giannis Antetokounmpo': 9, 'Tyrese Maxey': 4, 'Jalen Johnson': 14, 'Jalen Brunson': 54, 'Walker Kessler': 19,
    'Stephon Castle': 87, 'Payton Pritchard': 101, 'Cade Cunningham': 13, 'Pascal Siakam': 48, 'Jay Huff': 191,
    'Stephen Curry': 7, 'Jimmy Butler': 31, 'Julian Strawther': 427, 'Brandon Miller': 43, 'Onyeka Okongwu': 60,
    'Chet Holmgren': 47, 'Jaylen Brown': 24, 'Keyonte George': 29, 'Alperen Sengun': 20, 'Anthony Edwards': 18,
    'LaMelo Ball': 28, 'Rudy Gobert': 85, 'Jaden McDaniels': 84, 'Jonathan Kuminga': 252, 'Terrence Shannon': 497,
    'Joan Beringer': 438, 'Zach Edey': 56, 'Cedric Coward': 143, 'Jerami Grant': 126, 'Scotty Pippen': 139,
    'Jaylen Wells': 282, 'Isaiah Stewart': 210, 'Andrew Wiggins': 92, 'Davion Mitchell': 197, 'Pelle Larsson': 240,
    'Tim Hardaway': 270,
}


_season_totals_raw = season_totals


def season_totals(season, source='nba'):
    """Season totals; minutes filled from the game logs when the stored value is empty."""
    rows = _season_totals_raw(season, source)
    if any(not r['min'] for r in rows.values()):
        con = connect()
        mins = dict(con.execute("select player_pk, sum(min) from player_game_logs where season=? and season_type='regular' group by player_pk", (season,)))
        con.close()
        for p, r in rows.items():
            if not r['min']:
                r['min'] = float(mins.get(p) or 0)
    return rows
