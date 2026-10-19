"""Season H2H simulation of our league's real rosters (user, 2026-10-18), played day by day.

Expected values, not random draws (user: no Monte Carlo):
- Availability = projected GP / 82, capped at 1 (the same rule as `valuation/simulate.py`).
- Each game day, a player whose NBA team plays brings `availability x his per-game line`.
- Lineup: 10 starter slots (G G G F F F C, 3 Util). Players are taken best first (value = the value
  table's per-game total). A player fills `availability` of a slot; what he leaves open (the games he
  misses) goes to the next players. So a deep, healthy roster fills more of its 10 slots, and a bench
  player counts only on days when fewer than 10 starters play. Position slots first, then Util.
- A week sums the days of the Yahoo fantasy week; the 9 categories are compared per matchup (TO lower).
- Record: Yahoo H2H categories, every category counts as one win, loss or tie.

Not modeled: waiver adds, trades, IL replacements, real injuries, the day-to-day noise of a game.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

STAT_KEYS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
CATS = ("fg_pct", "ft_pct", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
SLOTS = {"G": 3, "F": 3, "C": 1, "Util": 3}
SEASON_GAMES = 82


@dataclass(frozen=True)
class SimPlayer:
    pk: int
    team: str | None  # NBA team
    positions: tuple[str, ...]  # subset of G, F, C
    value: float  # lineup order, higher first
    per_game: tuple[float, ...]  # STAT_KEYS order
    availability: float


@dataclass(frozen=True)
class Week:
    week: int
    first: date
    last: date

    def days(self) -> list[date]:
        return [self.first + timedelta(days=i) for i in range((self.last - self.first).days + 1)]


def sim_player(pk: int, row: dict) -> SimPlayer | None:
    """From a value table row (stats are season totals with gp). None without games."""
    s = row["stats"]
    gp = s.get("gp") or 0
    if gp <= 0:
        return None
    return SimPlayer(pk=pk, team=row.get("team"),
                     positions=tuple(p for p in (row.get("positions") or []) if p in ("G", "F", "C")),
                     value=row.get("total") if row.get("total") is not None else -99.0,
                     per_game=tuple((s.get(k) or 0) / gp for k in STAT_KEYS),
                     availability=min(gp / SEASON_GAMES, 1.0))


def day_line(players: list[SimPlayer]) -> tuple[list[float], float, float]:
    """One game day of one team: (stat sums, starter games used, games available).

    `players` are those whose NBA team plays today. Best first; each fills `availability` of a slot:
    first his own position slot with the most room, then Util.
    """
    room = dict(SLOTS)
    sums = [0.0] * len(STAT_KEYS)
    used = 0.0
    for p in sorted(players, key=lambda p: -p.value):
        left = p.availability
        for slot in sorted(p.positions, key=lambda s: -room[s]) + ["Util"]:
            take = min(left, room[slot])
            if take <= 0:
                continue
            room[slot] -= take
            left -= take
            used += take
            for i, x in enumerate(p.per_game):
                sums[i] += take * x
            if left <= 1e-12:
                break
    return sums, used, sum(p.availability for p in players)


def cat_values(sums: list[float]) -> dict[str, float]:
    s = dict(zip(STAT_KEYS, sums))
    return {"fg_pct": s["fgm"] / s["fga"] if s["fga"] else 0.0, "ft_pct": s["ftm"] / s["fta"] if s["fta"] else 0.0,
            "tpm": s["tpm"], "pts": s["pts"], "reb": s["reb"], "ast": s["ast"], "stl": s["stl"], "blk": s["blk"],
            "tov": s["tov"]}


def compare(a: dict[str, float], b: dict[str, float]) -> list[int]:
    """Per category from a's view: 1 win, -1 loss, 0 tie."""
    out = []
    for c in CATS:
        x, y = a[c], b[c]
        if abs(x - y) < 1e-9:
            out.append(0)
        else:
            out.append(1 if (x < y if c == "tov" else x > y) else -1)
    return out


def team_weeks(roster: list[SimPlayer], weeks: list[Week], plays: dict[date, set[str]]) -> list[dict]:
    """Per week: category values, starter games used, games available (all players), days."""
    out = []
    for w in weeks:
        sums = [0.0] * len(STAT_KEYS)
        used = avail = 0.0
        for d in w.days():
            teams = plays.get(d, set())
            s, u, a = day_line([p for p in roster if p.team in teams])
            sums = [x + y for x, y in zip(sums, s)]
            used += u
            avail += a
        out.append({"week": w.week, "cats": cat_values(sums), "used": used, "available": avail,
                    "slot_days": 10 * len(w.days())})
    return out


def season(rosters: dict[int, list[SimPlayer]], weeks: list[Week], plays: dict[date, set[str]],
           matchups: dict[int, list[tuple[int, int]]]) -> dict:
    """Every team's weekly lines, the scheduled matchups and the all-play record per week."""
    lines = {t: team_weeks(r, weeks, plays) for t, r in rosters.items()}
    record = defaultdict(lambda: [0, 0, 0])  # scheduled H2H, category W-L-T
    allplay = defaultdict(lambda: [0, 0, 0])  # every team vs every other team, every week
    results = []
    for wi, w in enumerate(weeks):
        for a in rosters:
            for b in rosters:
                if a != b:
                    r = compare(lines[a][wi]["cats"], lines[b][wi]["cats"])
                    allplay[a][0] += r.count(1)
                    allplay[a][1] += r.count(-1)
                    allplay[a][2] += r.count(0)
        for a, b in matchups.get(w.week, []):
            if a not in rosters or b not in rosters:
                continue
            r = compare(lines[a][wi]["cats"], lines[b][wi]["cats"])
            wa, la, ta = r.count(1), r.count(-1), r.count(0)
            record[a] = [record[a][0] + wa, record[a][1] + la, record[a][2] + ta]
            record[b] = [record[b][0] + la, record[b][1] + wa, record[b][2] + ta]
            results.append({"week": w.week, "a": a, "b": b, "cats": r, "score": [wa, la, ta]})
    return {"lines": lines, "results": results, "record": dict(record), "allplay": dict(allplay)}
