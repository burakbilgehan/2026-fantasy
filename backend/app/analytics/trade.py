"""Trade evaluator and trade finder (VISION M5, user, 2026-10-19).

A trade is judged on our side by the season H2H sim (`season_sim.py`): all-play category win share
(every team vs every team, every week; no schedule luck), the scheduled record and the per-category
win shares, before and after. Category lines are shown per game and as season totals.

Roster sizes stay as they were. The side that receives more players drops its weakest (we drop by our
value, the other manager by Yahoo value: managers trust Yahoo, user 2026-10-19). The side that gives more
adds the best free agents (we by our value, they by Yahoo value). Our gain is reported net of the
free-agent move we could make without the trade ("net"), so a 2-for-1 does not look good only because
of the open slot.

Will the other manager accept? A label from his Yahoo value change and his own sim change. Managers
weigh Yahoo values more than our models (user, 2026-10-19), so the Yahoo change leads.
"""

import itertools
from dataclasses import dataclass, field

from app.analytics import season_sim as ss

SLACK = 15.0  # largest Yahoo value a drop or free-agent add can move the first filter
OVERPAY = 8.0  # whole-league search: most Yahoo value my side may give away
COUNTING = ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")
CATS = ss.CATS


@dataclass
class Context:
    rows: dict[int, dict]  # player_pk -> value table row
    rosters: dict[int, list[int]]  # team -> player_pks
    names: dict[int, str]
    me: int
    weeks: list[ss.Week]
    matchups: dict[int, list[tuple[int, int]]]
    plays: dict
    sp: dict[int, ss.SimPlayer] = field(default_factory=dict)
    _cache: dict = field(default_factory=dict)

    def __post_init__(self):
        self.sp = {pk: s for pk, r in self.rows.items() if (s := ss.sim_player(pk, r))}
        owned = {pk for v in self.rosters.values() for pk in v}
        free = [pk for pk in self.sp if pk not in owned and not self.rows[pk].get("injury")]
        self.fa_ours = sorted(free, key=lambda pk: -self.ours(pk))
        self.fa_yahoo = sorted(free, key=lambda pk: -self.yahoo(pk))

    def ours(self, pk: int) -> float:
        return self.rows[pk].get("dollars") or 0.0

    def yahoo(self, pk: int) -> float:
        return (self.rows[pk].get("market") or {}).get("yahoo_auction_value") or 0.0

    def weeks_of(self, pks) -> list[dict]:
        key = frozenset(pks)
        if key not in self._cache:
            self._cache[key] = ss.team_weeks([self.sp[p] for p in key if p in self.sp], self.weeks, self.plays)
        return self._cache[key]


def team_line(rows: dict[int, dict], pks, mode: str) -> dict[str, float]:
    """Per game (games-weighted, like the League tab) or season totals. Percentages: makes / attempts."""
    st = [rows[p]["stats"] for p in pks if (rows[p]["stats"].get("gp") or 0) > 0]
    tot = lambda k: sum(s.get(k) or 0 for s in st)
    games = tot("gp") or 1
    line = {k: tot(k) / games if mode == "avg" else tot(k) for k in COUNTING}
    line["fg_pct"] = tot("fgm") / tot("fga") if tot("fga") else 0.0
    line["ft_pct"] = tot("ftm") / tot("fta") if tot("fta") else 0.0
    return line


def ranks(lines: dict[int, dict[str, float]]) -> dict[int, dict[str, int]]:
    out = {t: {} for t in lines}
    for c in CATS:
        for t, l in lines.items():
            better = sum(1 for u, m in lines.items() if u != t and (m[c] < l[c] if c == "tov" else m[c] > l[c]))
            out[t][c] = better + 1
    return out


NEAR = 3.0  # dollars: candidates this close to the weakest (or best) count as a tie, position balance decides
POS = ("G", "F", "C")


def _net_positions(ctx: Context, gained: list[int], lost: list[int]) -> dict[str, int]:
    """Per position: eligible players received minus sent (a G,F player counts in both)."""
    net = dict.fromkeys(POS, 0)
    for sign, pks in ((1, gained), (-1, lost)):
        for p in pks:
            for pos in ctx.rows[p].get("positions") or []:
                if pos in net:
                    net[pos] += sign
    return net


def _pos_score(ctx: Context, pk: int, net: dict[str, int]) -> float:
    ps = [p for p in (ctx.rows[pk].get("positions") or []) if p in net]
    return sum(net[p] for p in ps) / len(ps) if ps else 0.0


def _pick(ctx: Context, cands: list[int], value, net: dict[str, int], n: int, drop: bool) -> list[int]:
    """n players to drop (weakest first) or add (best first). A clear choice (more than NEAR away from the
    next one) is taken as is. Among near ties, position balance decides (user, 2026-10-19): drop from the
    position the trade gave the most, add at the position the trade took the most."""
    out = []
    net = dict(net)
    pool = sorted(cands, key=value, reverse=not drop)
    for _ in range(n):
        pool = [p for p in pool if p not in out]
        if not pool:
            break
        first = value(pool[0])
        near = [p for p in pool if abs(value(p) - first) <= NEAR]
        if len(near) == 1:
            choice = near[0]
        else:  # drop: most surplus position; add: most missing position; then the value order
            choice = max(near, key=lambda p: (_pos_score(ctx, p, net) if drop else -_pos_score(ctx, p, net),
                                              -value(p) if drop else value(p)))
        out.append(choice)
        for pos in ctx.rows[choice].get("positions") or []:
            if pos in net:
                net[pos] += -1 if drop else 1
    return out


def apply_trade(ctx: Context, give: list[int], get: list[int], partner: int) -> dict:
    """New rosters of both teams with the drops and free-agent adds that keep their sizes."""
    mine = [p for p in ctx.rosters[ctx.me] if p not in give] + list(get)
    theirs = [p for p in ctx.rosters[partner] if p not in get] + list(give)
    my_drop, my_add, their_drop, their_add = [], [], [], []
    my_net, their_net = _net_positions(ctx, get, give), _net_positions(ctx, give, get)
    extra = len(get) - len(give)
    if extra > 0:
        my_drop = _pick(ctx, [p for p in mine if p not in get], ctx.ours, my_net, extra, drop=True)
        mine = [p for p in mine if p not in my_drop]
        their_add = _pick(ctx, [p for p in ctx.fa_yahoo[:30] if p not in my_drop], ctx.yahoo, their_net, extra, drop=False)
        theirs += their_add
    elif extra < 0:
        their_drop = _pick(ctx, [p for p in theirs if p not in give], ctx.yahoo, their_net, -extra, drop=True)
        theirs = [p for p in theirs if p not in their_drop]
        my_add = _pick(ctx, [p for p in ctx.fa_ours[:30] if p not in their_drop], ctx.ours, my_net, -extra, drop=False)
        mine += my_add
    return {"mine": mine, "theirs": theirs, "my_drop": my_drop, "my_add": my_add,
            "their_drop": their_drop, "their_add": their_add}


def value_changes(ctx: Context, give: list[int], get: list[int], t: dict) -> dict:
    """Roster value changes with the drops and free-agent adds counted (user, 2026-10-19: a 1-for-2 costs my
    weakest player, a 2-for-1 gives me a free agent). Mine in our value, theirs in Yahoo value."""
    ours = sum(map(ctx.ours, get)) + sum(map(ctx.ours, t["my_add"])) - sum(map(ctx.ours, give)) - sum(map(ctx.ours, t["my_drop"]))
    their_yahoo = (sum(map(ctx.yahoo, give)) + sum(map(ctx.yahoo, t["their_add"]))
                   - sum(map(ctx.yahoo, get)) - sum(map(ctx.yahoo, t["their_drop"])))
    return {"ours": ours, "their_yahoo": their_yahoo}


def fa_only(ctx: Context, n: int) -> list[int]:
    """My roster after the move I could make without a trade: drop my n weakest, add the n best free agents."""
    if n <= 0:
        return list(ctx.rosters[ctx.me])
    drop = sorted(ctx.rosters[ctx.me], key=ctx.ours)[:n]
    return [p for p in ctx.rosters[ctx.me] if p not in drop] + ctx.fa_ours[:n]


def sim_view(ctx: Context, lines: dict[int, list[dict]], team: int) -> dict:
    """All-play share, per-category all-play shares and the scheduled record of one team."""
    ap = [0.0] * len(CATS)
    n = 0
    w = l = t = 0
    mine = lines[team]
    for wi, wk in enumerate(ctx.weeks):
        for other, ls in lines.items():
            if other == team:
                continue
            r = ss.compare(mine[wi]["cats"], ls[wi]["cats"])
            n += 1
            for i, x in enumerate(r):
                ap[i] += 1 if x == 1 else 0.5 if x == 0 else 0
        for a, b in ctx.matchups.get(wk.week, []):
            if team in (a, b):
                r = ss.compare(mine[wi]["cats"], lines[b if a == team else a][wi]["cats"])
                w, l, t = w + r.count(1), l + r.count(-1), t + r.count(0)
    return {"allplay": sum(ap) / (n * len(CATS)) if n else 0.0,
            "cats": {c: ap[i] / n if n else 0.0 for i, c in enumerate(CATS)},
            "record": [w, l, t], "used": sum(x["used"] for x in mine)}


def _lines(ctx: Context, changes: dict[int, list[int]]) -> dict[int, list[dict]]:
    return {t: ctx.weeks_of(changes.get(t, pks)) for t, pks in ctx.rosters.items()}


def quick_gain(ctx: Context, mine: list[int], theirs: list[int], partner: int) -> tuple[dict, dict]:
    """(my sim view after, partner sim view after) with only these two rosters changed."""
    lines = _lines(ctx, {ctx.me: mine, partner: theirs})
    return sim_view(ctx, lines, ctx.me), sim_view(ctx, lines, partner)


def evaluate(ctx: Context, give: list[int], get: list[int], partner: int) -> dict:
    tr = apply_trade(ctx, give, get, partner)
    before_r = {t: list(v) for t, v in ctx.rosters.items()}
    after_r = dict(before_r) | {ctx.me: tr["mine"], partner: tr["theirs"]}
    lb, la = _lines(ctx, {}), _lines(ctx, {ctx.me: tr["mine"], partner: tr["theirs"]})
    fa_r = fa_only(ctx, len(tr["my_add"]))
    lf = _lines(ctx, {ctx.me: fa_r})

    def side(team: int) -> dict:
        out = {}
        for mode in ("avg", "total"):
            b = {t: team_line(ctx.rows, v, mode) for t, v in before_r.items()}
            a = {t: team_line(ctx.rows, v, mode) for t, v in after_r.items()}
            rb, ra = ranks(b), ranks(a)
            out[mode] = {"before": b[team], "after": a[team], "rank_before": rb[team], "rank_after": ra[team]}
        out["sim_before"] = sim_view(ctx, lb, team)
        out["sim_after"] = sim_view(ctx, la, team)
        return out

    me_side, them_side = side(ctx.me), side(partner)
    fa_view = sim_view(ctx, lf, ctx.me)

    def fixture(lines: dict[int, list[dict]]) -> list[dict]:
        out = []
        for wi, wk in enumerate(ctx.weeks):
            m = next(((a, b) for a, b in ctx.matchups.get(wk.week, []) if ctx.me in (a, b)), None)
            if not m:
                out.append({"week": wk.week, "first": wk.first.isoformat(), "last": wk.last.isoformat(),
                            "opponent": None, "score": None, "used": lines[ctx.me][wi]["used"]})
                continue
            opp = m[1] if m[0] == ctx.me else m[0]
            r = ss.compare(lines[ctx.me][wi]["cats"], lines[opp][wi]["cats"])
            out.append({"week": wk.week, "first": wk.first.isoformat(), "last": wk.last.isoformat(), "opponent": opp, "score": [r.count(1), r.count(-1), r.count(0)], "cats": r,
                        "used": lines[ctx.me][wi]["used"], "opp_used": lines[opp][wi]["used"]})
        return out

    val = lambda pks, f: round(sum(f(p) for p in pks), 1)
    vc = value_changes(ctx, give, get, tr)
    return {
        "partner": partner,
        "give": give, "get": get,
        "my_drop": tr["my_drop"], "my_add": tr["my_add"], "their_drop": tr["their_drop"], "their_add": tr["their_add"],
        "names": {p: ctx.rows[p]["name"] for p in tr["my_add"] + tr["their_add"]},  # free agents are on no roster
        "values": {"give_yahoo": val(give, ctx.yahoo), "get_yahoo": val(get, ctx.yahoo),
                   "give_ours": val(give, ctx.ours), "get_ours": val(get, ctx.ours),
                   "my_drop_ours": val(tr["my_drop"], ctx.ours), "my_add_ours": val(tr["my_add"], ctx.ours),
                   "their_drop_yahoo": val(tr["their_drop"], ctx.yahoo), "their_add_yahoo": val(tr["their_add"], ctx.yahoo),
                   "ours_change": round(vc["ours"], 1), "their_yahoo_change": round(vc["their_yahoo"], 1)},
        "me": me_side, "them": them_side,
        "net_allplay": me_side["sim_after"]["allplay"] - fa_view["allplay"],
        "fa_only_allplay": fa_view["allplay"],
        "fixture_before": fixture(lb), "fixture_after": fixture(la),
        # They receive what I give.
        "accept": accept_label(vc["their_yahoo"],
                               them_side["sim_after"]["allplay"] - them_side["sim_before"]["allplay"]),
    }


def accept_label(their_yahoo_gain: float, their_sim_gain: float) -> str:
    """Yahoo value decides (managers trust it more than fit, user 2026-10-19); a big loss in their own
    sim moves the label one step down, because a manager may still see his weak categories get worse."""
    level = 0 if their_yahoo_gain >= 0 else 1 if their_yahoo_gain >= -3 else 2
    if their_sim_gain < -0.04:
        level += 1
    return ("likely", "maybe", "hard", "hard")[level]


def find(ctx: Context, give: list[int], get: list[int], improve: list[str], partner: int | None = None,
         max_size: int = 3, min_their_yahoo: float = -4.0, limit: int = 1000) -> list[dict]:
    """Trades around the players I put in. Give only: every other roster's 1..len(give)+1 player sets.
    Get only (targets): my 1..len(get)+1 player sets for them, from their owner. Both: those, plus at most
    one more player on each side. Nothing put in: the whole league, 1-1, 1-2, 2-1 and 2-2, where my side gives
    at most OVERPAY Yahoo value more than it gets (bigger gifts are not worth a search). No partner: every team.
    Ranked by my net all-play gain plus the categories I asked to improve."""
    owner = {pk: t for t, v in ctx.rosters.items() for pk in v}
    open_search = not give and not get
    if get:
        partners = [owner[get[0]]]
    else:
        partners = [partner] if partner else [t for t in ctx.rosters if t != ctx.me]
    lines0 = _lines(ctx, {})
    base = sim_view(ctx, lines0, ctx.me)
    base_them = {t: sim_view(ctx, lines0, t) for t in partners}
    fa_base = {}
    cands = []
    mine_pool = [p for p in ctx.rosters[ctx.me] if p not in give]
    for t in partners:
        their_pool = [p for p in ctx.rosters[t] if p not in get]
        if give and get:
            gives = [tuple(give)] + [tuple(give) + (p,) for p in mine_pool]
            gets = [tuple(get)] + [tuple(get) + (p,) for p in their_pool]
        elif give:
            gives = [tuple(give)]
            gets = [c for k in range(1, min(max_size, len(give) + 1) + 1) for c in itertools.combinations(their_pool, k)]
        elif get:
            gives = [c for k in range(1, min(max_size, len(get) + 1) + 1) for c in itertools.combinations(mine_pool, k)]
            gets = [tuple(get)]
        else:
            n = min(max_size, 2)
            gives = [c for k in range(1, n + 1) for c in itertools.combinations(mine_pool, k)]
            gets = [c for k in range(1, n + 1) for c in itertools.combinations(their_pool, k)]
        for g in gives:
            gy, gmax = sum(map(ctx.yahoo, g)), max(map(ctx.yahoo, g))
            for r in gets:
                ry = sum(map(ctx.yahoo, r))
                their_gain = gy - ry  # before drops and adds: a loose first filter, the exact one is below
                if their_gain < min_their_yahoo - SLACK or (open_search and their_gain > OVERPAY + SLACK):
                    continue
                if max(map(ctx.yahoo, r)) > gmax + 8:  # a star for spare parts: nobody takes it
                    continue
                cands.append((t, list(g), list(r), their_gain))
    out = []
    for t, g, r, _ in cands:
        tr = apply_trade(ctx, g, r, t)
        vc = value_changes(ctx, g, r, tr)
        their_gain = vc["their_yahoo"]
        if their_gain < min_their_yahoo or (open_search and their_gain > OVERPAY):
            continue
        mine_after, them_after = quick_gain(ctx, tr["mine"], tr["theirs"], t)
        k = len(tr["my_add"])
        if k not in fa_base:
            fa_base[k] = sim_view(ctx, _lines(ctx, {ctx.me: fa_only(ctx, k)}), ctx.me)
        net = mine_after["allplay"] - fa_base[k]["allplay"]
        cat_gain = {c: mine_after["cats"][c] - base["cats"][c] for c in CATS}
        if improve and any(cat_gain[c] < 0 for c in improve):
            continue
        score = net + 0.5 * sum(cat_gain[c] for c in improve) / max(len(improve), 1)
        their_sim = them_after["allplay"] - base_them[t]["allplay"]
        out.append({"partner": t, "give": g, "get": r, "my_drop": tr["my_drop"], "my_add": tr["my_add"],
                    "net_allplay": net, "allplay_after": mine_after["allplay"], "score": score,
                    "record_after": mine_after["record"], "cat_gain": cat_gain,
                    "their_yahoo_gain": their_gain, "their_sim_gain": their_sim,
                    "ours_gain": vc["ours"], "their_drop": tr["their_drop"], "their_add": tr["their_add"],
                    "names": {p: ctx.rows[p]["name"] for p in tr["my_add"] + tr["their_add"]},
                    "accept": accept_label(their_gain, their_sim)})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]
