"""Stat and price tables for one player, written by code from the DB.

The same tables go into the LLM prompt and into the rendered profile, so the
LLM never writes a number of its own. Per game = total / GP. Past seasons come
from stats.nba.com (source `nba`); their minutes are not in the season rows, so
MIN is the mean of the regular season game logs.
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Draft, DraftPick, PlayerExternalId, PlayerGameLog, PlayerMarketValue, PlayerProjection,
    PlayerSeasonStats,
)
from app.seasons import CURRENT_SEASON, label, previous, start_year

PAST_SEASONS = [label(start_year(CURRENT_SEASON) - n) for n in (3, 2, 1)]
PROJECTION_SOURCES = ("yahoo", "espn")
MARKET_SOURCES = ("yahoo", "espn")


@dataclass
class StatRow:
    label: str
    gp: float
    mpg: float | None
    totals: dict  # fgm fga ftm fta tpm pts reb ast stl blk tov


@dataclass
class PriceRow:
    source: str
    auction_value: float | None
    average_cost: float | None
    rank: int | None
    injury: str | None = None
    injury_note: str | None = None


@dataclass
class PlayerNumbers:
    rows: list[StatRow] = field(default_factory=list)
    prices: list[PriceRow] = field(default_factory=list)
    league_price: int | None = None  # our league's last auction, None = not drafted
    league_season: str = previous(CURRENT_SEASON)

    @property
    def injury(self) -> str | None:
        """Yahoo injury status now, like "Q (Not Injury Related)"."""
        for p in self.prices:
            if p.source == "yahoo" and p.injury:
                return f"{p.injury} ({p.injury_note})" if p.injury_note else p.injury
        return None


_COLS = ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


def _totals(r) -> dict:
    return {c: getattr(r, c) for c in _COLS}


def load(db: Session, player_pk: int) -> PlayerNumbers:
    out = PlayerNumbers()
    seasons = {r.season: r for r in db.scalars(select(PlayerSeasonStats).where(
        PlayerSeasonStats.player_pk == player_pk, PlayerSeasonStats.source == "nba",
        PlayerSeasonStats.season.in_(PAST_SEASONS)))}
    mins = dict(db.execute(select(PlayerGameLog.season, func.avg(PlayerGameLog.min)).where(
        PlayerGameLog.player_pk == player_pk, PlayerGameLog.source == "nba",
        PlayerGameLog.season_type == "regular").group_by(PlayerGameLog.season)).all())
    for s in PAST_SEASONS:
        if (r := seasons.get(s)) and r.gp:
            out.rows.append(StatRow(s, r.gp, mins.get(s), _totals(r)))
    projs = {r.source: r for r in db.scalars(select(PlayerProjection).where(
        PlayerProjection.player_pk == player_pk, PlayerProjection.season == CURRENT_SEASON))}
    for src in PROJECTION_SOURCES:
        if (r := projs.get(src)) and r.gp:
            out.rows.append(StatRow(f"{CURRENT_SEASON} proj, {src.capitalize() if src != 'espn' else 'ESPN'}",
                                    r.gp, r.min / r.gp if r.min else None, _totals(r)))
    markets = {r.source: r for r in db.scalars(select(PlayerMarketValue).where(
        PlayerMarketValue.player_pk == player_pk, PlayerMarketValue.season == CURRENT_SEASON))}
    for src in MARKET_SOURCES:
        if (m := markets.get(src)):
            out.prices.append(PriceRow(src, m.auction_value, m.average_cost, m.rank, m.injury, m.injury_note))
    out.league_price = db.scalar(
        select(DraftPick.price).join(Draft, Draft.id == DraftPick.draft_pk)
        .join(PlayerExternalId, (PlayerExternalId.external_id == DraftPick.yahoo_player_id)
              & (PlayerExternalId.source == "yahoo"))
        .where(Draft.kind == "past_league", Draft.season == out.league_season,
               PlayerExternalId.player_pk == player_pk))
    return out


def _f(v: float | None, nd: int = 1) -> str:
    return "-" if v is None else f"{v:.{nd}f}"


def _pct(made: float, att: float) -> str:
    return "-" if not att else f"{100 * made / att:.1f}"


def stat_table(n: PlayerNumbers) -> str:
    if not n.rows:
        return "No NBA stats and no projections in our data."
    head = ("| Per game | GP | MIN | FG% (FGA) | FT% (FTA) | 3PM | PTS | REB | AST | STL | BLK | TO |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for r in n.rows:
        t, g = r.totals, r.gp
        pg = {c: t[c] / g for c in _COLS}
        lines.append(
            f"| {r.label} | {g:.0f} | {_f(r.mpg)} | {_pct(t['fgm'], t['fga'])} ({pg['fga']:.1f}) | "
            f"{_pct(t['ftm'], t['fta'])} ({pg['fta']:.1f}) | {pg['tpm']:.1f} | {pg['pts']:.1f} | "
            f"{pg['reb']:.1f} | {pg['ast']:.1f} | {pg['stl']:.1f} | {pg['blk']:.1f} | {pg['tov']:.1f} |")
    return "\n".join(lines)


def price_table(n: PlayerNumbers) -> str:
    by = {p.source: p for p in n.prices}
    y, e = by.get("yahoo"), by.get("espn")
    league = "not drafted" if n.league_price is None else str(n.league_price)
    return (
        f"| Price in USD | Yahoo value | Yahoo average cost | Yahoo rank | ESPN value | ESPN average cost | ESPN rank | Our league {n.league_season} |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| {CURRENT_SEASON} | {_f(y and y.auction_value, 0)} | {_f(y and y.average_cost)} | {y.rank if y and y.rank else '-'} "
        f"| {_f(e and e.auction_value, 0)} | {_f(e and e.average_cost)} | {e.rank if e and e.rank else '-'} | {league} |")
