"""Room simulation (the Sim page; research seed for T-030): an auction among 12 managers who value players
differently, then a Monte Carlo season on expected weekly lines with week-to-week noise.

Auction: managers nominate in turn (the available player they value most). Every manager with an open slot
bids his own value for the player times a lognormal noise, capped by `bid_cap`: the money that leaves his
reserve per other open slot (`Manager.reserve`, default 1 USD = the old rule; a budget plan sets more, so a
manager cannot spend himself out of the tier he planned to fill the roster with). A manager with `spend_down`
also raises his value when his money outgrows his own values of the best players left (`spend_factor`), so
he does not end with money nobody can use. The highest bid wins and pays the second-highest bid plus 1 (an English auction), at least 1 USD.
Money left at the end is wasted, as in a real room.

Season: team weekly lines = the roster's expected lines (per game x games that week x availability,
`simulate.expected_lines`) plus noise. Counting stats and attempts: normal with variance NOISE x mean
(overdispersion measured on the 2024-25 and 2025-26 game logs). Makes: binomial around the sampled attempts.
Regular season = all weeks but the last `playoff_weeks`; one opponent per week (round robin); playoffs:
the top 8 by wins (ties by category share), fixed bracket 1-8, 4-5, 2-7, 3-6, higher seed wins a tied week
(docs/RULES.md). Pure numpy, no DB.
"""

from dataclasses import dataclass, field

import numpy as np

from app.analytics.valuation.simulate import _I, STAT_KEYS, SimInputs, cat_lines, expected_lines

# Variance of a weekly total around its expected value, divided by the expected value (median over players
# with 15+ weeks, 2024-25 and 2025-26 logs, 2026-10-13). fgm and ftm: variance over the binomial variance.
NOISE = {"tpm": 1.20, "pts": 3.76, "reb": 1.56, "ast": 1.36, "stl": 1.06, "blk": 1.07, "tov": 1.04,
         "fga": 1.86, "fta": 2.24, "fgm": 0.85, "ftm": 0.97}


@dataclass
class Manager:
    name: str
    style: str
    values: dict  # player -> dollars this manager is willing to pay (before bid noise)
    mine: bool = False
    noise: float = 0.12  # lognormal sigma of each bid
    money: int = 200
    slots: int = 12
    roster: list = field(default_factory=list)
    paid: dict = field(default_factory=dict)
    stars: set = field(default_factory=set)  # players this manager chases above value (values holds the raised bid)
    max_stars: int = 0  # after this many of them are won, the rest are valued at plain_values
    plain_values: dict = field(default_factory=dict)
    reserve: float = 1.0  # USD kept back for each other open slot (budget plan); see bid_cap
    spend_down: bool = False  # raise bids when his money outgrows what is left to buy; see spend_factor


def bid_cap(money: int, slots: int, reserve: float, min_bid: int = 1) -> int:
    """Highest bid a manager may make: his money minus `reserve` for each other open slot. When his money is
    already below the reserve per slot (the plan is broken), the reserve drops to an even split of what is
    left, so he can still fill the roster. Never below the hard rule of `min_bid` per other open slot."""
    if slots <= 0:
        return 0
    r = max(float(min_bid), min(float(reserve), money / slots))
    return int(np.floor(money - (slots - 1) * r + 1e-9))


SPEND_MAX = 3.0  # highest spend-down factor


def spend_factor(money: int, slots: int, best_left: np.ndarray) -> float:
    """Spend-down: money left at the end is wasted, so a good drafter whose money is more than his own values of
    the best `slots` players still available raises his bids by money / that sum (1 to SPEND_MAX)."""
    top = np.sort(best_left)[-slots:] if slots > 0 else best_left[:0]
    need = float(top[top > 0].sum())
    if need <= 0:
        return SPEND_MAX
    return min(SPEND_MAX, max(1.0, money / need))


def auction(managers: list[Manager], order: list, rng: np.random.Generator, min_bid: int = 1) -> list[dict]:
    """Runs the draft in place (rosters, money, paid). `order`: players by market price, used when a nominator
    values nobody left. Returns the log: one row per sale."""
    available = {p for m in managers for p in m.values} | set(order)
    rank = {p: i for i, p in enumerate(order)}
    log: list[dict] = []
    turn = 0
    universe = sorted(available, key=lambda q: rank.get(q, 10**9))
    pos = {q: i for i, q in enumerate(universe)}
    open_ = np.ones(len(universe), dtype=bool)
    plain = {id(m): np.array([(m.plain_values or m.values).get(q, 0.0) for q in universe])
             for m in managers if m.spend_down}
    while any(m.slots > 0 for m in managers) and available:
        nominator = managers[turn % len(managers)]
        turn += 1
        if nominator.slots == 0:
            continue
        wanted = [p for p in available if nominator.values.get(p, 0) > 0]
        p = max(wanted, key=lambda q: nominator.values[q]) if wanted else min(available, key=lambda q: rank.get(q, 10**9))
        bids = []
        for m in managers:
            if m.slots == 0:
                continue
            cap = bid_cap(m.money, m.slots, m.reserve, min_bid)
            base_value = m.values.get(p, 0.0)
            if p in m.stars and sum(1 for q in m.roster if q in m.stars) >= m.max_stars:
                base_value = min(base_value, m.plain_values.get(p, base_value))
            if m.spend_down:
                base_value *= spend_factor(m.money, m.slots, plain[id(m)][open_])
            w = int(round(base_value * float(np.exp(rng.normal(0.0, m.noise)))))
            w = min(w, cap)
            if m is nominator:
                w = max(w, min_bid)
            if w >= min_bid:
                bids.append((w, float(rng.random()), m))
        bids.sort(key=lambda b: (b[0], b[1]), reverse=True)
        w1, _, winner = bids[0]
        w2 = bids[1][0] if len(bids) > 1 else 0
        price = max(min_bid, min(w1, w2 + 1))
        winner.roster.append(p)
        winner.paid[p] = price
        winner.money -= price
        winner.slots -= 1
        available.discard(p)
        open_[pos[p]] = False
        log.append({"pick": len(log) + 1, "player": p, "nominator": nominator.name, "winner": winner.name,
                    "price": price, "second": w2, "bidders": len(bids)})
    return log


def round_robin(n: int) -> list[list[tuple[int, int]]]:
    """Circle method: n-1 rounds, every team plays once per round."""
    teams = list(range(n))
    rounds = []
    for _ in range(n - 1):
        rounds.append([(teams[i], teams[n - 1 - i]) for i in range(n // 2)])
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def sample_lines(T: np.ndarray, rng: np.random.Generator, seasons: int) -> np.ndarray:
    """Weekly stat lines with noise. T (teams, weeks, 11) expected -> (seasons, teams, weeks, 11)."""
    f = np.array([NOISE[k] for k in STAT_KEYS])
    mean = T[None]
    z = rng.standard_normal((seasons, *T.shape))
    x = mean + np.sqrt(np.maximum(f * mean, 0.0)) * z
    for mk, att in (("fgm", "fga"), ("ftm", "fta")):
        a = np.maximum(x[..., _I[att]], 0.0)
        p = np.divide(mean[..., _I[mk]], mean[..., _I[att]], out=np.zeros_like(mean[..., _I[mk]]), where=mean[..., _I[att]] > 0)
        x[..., _I[mk]] = a * p + np.sqrt(np.maximum(NOISE[mk] * a * p * (1.0 - p), 0.0)) * z[..., _I[mk]]
        x[..., _I[att]] = a
    return np.maximum(x, 0.0)


def play(rosters: list[list], rows: dict, basis: str, inputs: SimInputs, rng: np.random.Generator,
         seasons: int = 300, playoff_weeks: int = 3, playoff_teams: int = 8) -> dict:
    """Monte Carlo season for the rosters. Shares in percent; wins and losses are means over the seasons."""
    players, e = expected_lines(rows, basis, inputs)
    idx = {p: i for i, p in enumerate(players)}
    zero = np.zeros(e.shape[1:])
    T = np.stack([e[[idx[p] for p in r if p in idx]].sum(axis=0) if any(p in idx for p in r) else zero for r in rosters])
    n, W = T.shape[0], T.shape[1]
    L = cat_lines(sample_lines(T, rng, seasons))  # (S, n, W, 9)
    win = (L[:, :, None] > L[:, None]).astype(np.float32) + 0.5 * (L[:, :, None] == L[:, None])  # (S, n, n, W, 9)
    off = ~np.eye(n, dtype=bool)
    cat_share = win[:, off].reshape(seasons, n, n - 1, W, 9).mean(axis=(2, 3, 4))  # (S, n)
    per_cat = win[:, off].reshape(seasons, n, n - 1, W, 9).mean(axis=(0, 2, 3))  # (n, 9)
    reg = max(W - playoff_weeks, 1)
    sched = round_robin(n)
    wins = np.zeros((seasons, n))
    for w in range(reg):
        for a, b in sched[w % len(sched)]:
            cats = win[:, a, b, w].sum(-1)
            wins[:, a] += (cats > 4.5) + 0.5 * (cats == 4.5)
            wins[:, b] += (cats < 4.5) + 0.5 * (cats == 4.5)
    playoffs = np.zeros(n)
    titles = np.zeros(n)
    k = min(playoff_teams, n)
    for s in range(seasons):
        seeds = list(np.lexsort((-cat_share[s], -wins[s]))[:k])
        playoffs[seeds] += 1
        pairs = [(seeds[i], seeds[k - 1 - i]) for i in range(k // 2)]
        pairs = [pairs[i] for i in (0, 3, 1, 2)] if k == 8 else pairs  # 1-8, 4-5, 2-7, 3-6: no reseeding
        alive = [a for pair in pairs for a in pair]
        for w in range(reg, W):
            nxt = []
            for i in range(0, len(alive) - 1, 2):
                a, b = alive[i], alive[i + 1]
                cats = float(win[s, a, b, w].sum())
                nxt.append(a if cats > 4.5 or (cats == 4.5 and seeds.index(a) < seeds.index(b)) else b)
            alive = nxt
            if len(alive) == 1:
                break
        titles[alive[0]] += 1
    return {"cat_share": (100 * cat_share.mean(0)).tolist(), "wins": wins.mean(0).tolist(), "games": reg,
            "playoffs": (100 * playoffs / seasons).tolist(), "titles": (100 * titles / seasons).tolist(),
            "per_cat": (100 * per_cat).tolist(), "weeks": W, "seasons": seasons}
