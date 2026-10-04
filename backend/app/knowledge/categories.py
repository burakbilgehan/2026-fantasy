"""Category profile per player: where he is a real outlier, computed by code.

The LLM tends to call every good category a "specialist" and every weak one a
"punt fit" (user, 2026-10-04: too shallow). Category tags must rest on real
outliers, so code computes them and the tag gate (`allowed`) enforces them.

Basis: 2026-27 projections per game, mean of Yahoo and ESPN. Pool: players with
a Yahoo or ESPN rank within the top 250. FG% and FT% use volume-weighted impact
((player % - pool %) * attempts). TO is flipped so a higher z is always better.
Two z-scores per category:
- league z: against the whole pool. Specialist, anchor and liability tags use it.
- position z: against players of the same position (G, F, C; multi-eligible
  players get the mean of their groups). Punt fit tags use it: a guard with few
  blocks is normal for a guard and is not a punt BLK fit.
Thresholds: see STRONG, WEAK, POS_WEAK. Tuned on the pilot players (inferred
from the outputs, not a fitted rule).
"""

from dataclasses import dataclass, field
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlayerMarketValue, PlayerProjection
from app.seasons import CURRENT_SEASON

CATS = ("FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK", "TO")
POOL_RANK = 250
STRONG = 2.0     # league z for specialist / anchor / low TO (1.5 gave Trae Young PTS and 3PM: too loose)
WEAK = -1.5      # league z for liability / high TO
POS_WEAK = -1.0  # position z for a punt fit
POS_STRONG = 1.5  # position z, used for "AST from a big"
MAX_PUNTS = 2     # punt fit tags only for his two weakest categories
NO_3PM = 0.3     # threes per game below this = "no 3PM"


@dataclass
class Profile:
    per_game: dict[str, float]
    league_z: dict[str, float]
    pos_z: dict[str, float]
    groups: list[str]
    in_pool: bool

    def strengths(self) -> list[str]:
        return [c for c in CATS if self.league_z[c] >= STRONG]

    def weaknesses(self) -> list[str]:
        return [c for c in CATS if self.league_z[c] <= WEAK]

    def pos_weaknesses(self) -> list[str]:
        """Punt fit categories: weak for his position, among his MAX_PUNTS weakest, and his
        value without the category is positive. A player weak in five categories is a low
        value player, not a punt fit for five builds (user, 2026-10-04)."""
        weak = sorted((c for c in CATS if self.pos_z[c] <= POS_WEAK), key=lambda c: self.pos_z[c])[:MAX_PUNTS]
        total = sum(self.league_z.values())
        return [c for c in weak if total - self.league_z[c] >= 0]

    def prompt_block(self) -> str:
        lines = ["| Category | Per game | z vs pool | z vs position | Flag |", "|---|---|---|---|---|"]
        for c in CATS:
            flags = []
            if c in self.strengths():
                flags.append("league outlier, strong")
            if c in self.weaknesses():
                flags.append("league outlier, weak")
            if c in self.pos_weaknesses():
                flags.append("weak for his position (punt fit)")
            v = self.per_game[c]
            shown = f"{100 * v:.1f}%" if c in ("FG%", "FT%") else f"{v:.1f}"
            lines.append(f"| {c} | {shown} | {self.league_z[c]:+.1f} | {self.pos_z[c]:+.1f} | {', '.join(flags) or '-'} |")
        return "\n".join(lines)


@dataclass
class Pool:
    rows: dict[int, dict[str, float]]          # player_pk -> raw per game (fgm, fga, ...)
    groups: dict[int, list[str]]               # player_pk -> ["G", "F"]
    pct: dict[str, float] = field(default_factory=dict)
    stats: dict[str, tuple[float, float]] = field(default_factory=dict)  # cat -> (mean, sd) league
    pos_stats: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)

    def values(self, r: dict[str, float]) -> dict[str, float]:
        """Category values used for z: impact for percentages, -TO."""
        return {
            "FG%": (r["fgm"] / r["fga"] - self.pct["fg"]) * r["fga"] if r["fga"] else 0.0,
            "FT%": (r["ftm"] / r["fta"] - self.pct["ft"]) * r["fta"] if r["fta"] else 0.0,
            "3PM": r["tpm"], "PTS": r["pts"], "REB": r["reb"], "AST": r["ast"],
            "STL": r["stl"], "BLK": r["blk"], "TO": -r["tov"],
        }

    def profile(self, pk: int, raw: dict[str, float] | None = None, groups: list[str] | None = None) -> Profile | None:
        r = raw or self.rows.get(pk)
        if r is None:
            return None
        gs = groups or self.groups.get(pk) or ["G", "F", "C"]
        v = self.values(r)
        lz = {c: (v[c] - self.stats[c][0]) / self.stats[c][1] for c in CATS}
        pz = {}
        for c in CATS:
            m = mean(self.pos_stats[g][c][0] for g in gs if g in self.pos_stats)
            s = mean(self.pos_stats[g][c][1] for g in gs if g in self.pos_stats)
            pz[c] = (v[c] - m) / s
        per_game = {"FG%": r["fgm"] / r["fga"] if r["fga"] else 0.0, "FT%": r["ftm"] / r["fta"] if r["fta"] else 0.0,
                    "3PM": r["tpm"], "PTS": r["pts"], "REB": r["reb"], "AST": r["ast"], "STL": r["stl"],
                    "BLK": r["blk"], "TO": r["tov"]}
        return Profile(per_game, lz, pz, gs, pk in self.rows)


_COLS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def per_game_projection(db: Session, pk: int) -> dict[str, float] | None:
    rows = [r for r in db.scalars(select(PlayerProjection).where(
        PlayerProjection.player_pk == pk, PlayerProjection.season == CURRENT_SEASON,
        PlayerProjection.source.in_(("yahoo", "espn")))) if r.gp]
    if not rows:
        return None
    return {c: mean(getattr(r, c) / r.gp for r in rows) for c in _COLS}


def load_pool(db: Session) -> Pool:
    pks = set(db.scalars(select(PlayerMarketValue.player_pk).where(
        PlayerMarketValue.season == CURRENT_SEASON, PlayerMarketValue.rank <= POOL_RANK)))
    rows = {pk: r for pk in pks if (r := per_game_projection(db, pk))}
    groups = {}
    for pk, pos in db.execute(select(PlayerMarketValue.player_pk, PlayerMarketValue.positions).where(
            PlayerMarketValue.source == "yahoo", PlayerMarketValue.season == CURRENT_SEASON,
            PlayerMarketValue.player_pk.in_(rows))):
        groups[pk] = [g for g in ("G", "F", "C") if g in (pos or [])]
    pool = Pool(rows, groups)
    tot = {c: sum(r[c] for r in rows.values()) for c in ("fgm", "fga", "ftm", "fta")}
    pool.pct = {"fg": tot["fgm"] / tot["fga"], "ft": tot["ftm"] / tot["fta"]}
    vals = {pk: pool.values(r) for pk, r in rows.items()}
    pool.stats = {c: (mean(v[c] for v in vals.values()), pstdev([v[c] for v in vals.values()])) for c in CATS}
    for g in ("G", "F", "C"):
        members = [vals[pk] for pk in rows if g in (groups.get(pk) or [])]
        pool.pos_stats[g] = {c: (mean(v[c] for v in members), pstdev([v[c] for v in members])) for c in CATS}
    return pool


def allowed(rule: str | None, prof: Profile | None, injury: str | None, sources: list[str]) -> tuple[bool, str]:
    """Gate for one tag. `rule` comes from the tag registry. (ok, reason when not ok)."""
    if not rule:
        return True, ""
    kind, _, cat = rule.partition(":")
    if kind == "injury":
        ok = bool(injury) or any(s != "stats" for s in sources)
        return ok, "" if ok else "no injury status and no note"
    if prof is None:
        return False, "no projection, no category profile"
    if kind == "strong":
        ok = prof.league_z[cat] >= STRONG
        return ok, "" if ok else f"{cat} z {prof.league_z[cat]:+.1f} vs pool, needs {STRONG:+.1f}"
    if kind == "weak":
        ok = prof.league_z[cat] <= WEAK
        return ok, "" if ok else f"{cat} z {prof.league_z[cat]:+.1f} vs pool, needs {WEAK:+.1f}"
    if kind == "posweak":
        ok = cat in prof.pos_weaknesses()
        if ok:
            return True, ""
        if prof.pos_z[cat] > POS_WEAK:
            return False, f"{cat} z {prof.pos_z[cat]:+.1f} vs position, needs {POS_WEAK:+.1f}"
        return False, f"{cat} is not one of his {MAX_PUNTS} weakest, or he has no value without it"
    if kind == "bigstrong":
        ok = prof.groups != ["G"] and "G" not in prof.groups and prof.pos_z[cat] >= POS_STRONG
        return ok, "" if ok else f"not a F/C with {cat} z >= {POS_STRONG:+.1f} vs position"
    if kind == "no3pm":
        ok = prof.per_game["3PM"] < NO_3PM
        return ok, "" if ok else f"3PM {prof.per_game['3PM']:.1f} per game"
    if kind == "noweak":
        weak = prof.weaknesses() + [c for c in CATS if prof.pos_z[c] <= POS_WEAK]
        return not weak, "" if not weak else f"weak in {', '.join(sorted(set(weak)))}"
    raise ValueError(f"unknown tag rule {rule!r}")
