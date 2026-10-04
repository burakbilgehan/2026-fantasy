"""ESPN fantasy player feed: projections, ADP, average auction price.

URL: lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/segments/0/leaguedefaults/1
view=kona_player_info, header x-fantasy-filter. Public, no login (verified
2026-10-04). Undocumented: sync on demand only. Raw copies in data/raw/espn/.

Stat blocks per player (id = split + source + season, ESPN names a season by its end year):
- "10{year}": ESPN projection, totals plus averageStats. Used.
- "10{year-1}": ESPN preseason projection of last season. Stored as a projection of that season
  (lets us measure how good ESPN projections were).
- "00{year-1}": last season actual totals. Not used: stats.nba.com is the source for past seasons.
- per-game blocks (statSplitTypeId 5) for last season. Not used.

Market values (mapping inferred, not documented by ESPN):
- auction_value, rank: draftRanksByRankType.ROTO (categories). STANDARD (points) goes to extra.
- average_cost: ownership.auctionValueAverage (ESPN public auction drafts).
- average_pick: ownership.averageDraftPosition. Undrafted players sit near 140; see DATA_SOURCES.md.
"""

import json
from typing import Any

import httpx

from app.seasons import CURRENT_SEASON, end_year, previous
from app.sources.players.base import MarketValue, SourcePlayer, StatLine, save_raw
from app.sources.teams import canonical

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}"
PLAYERS_URL = BASE + "/segments/0/leaguedefaults/1"
LIMIT = 1000  # the feed is sorted by ESPN rank; projections end near rank 350
MIN_PLAYERS = 300

# ESPN stat ids -> our fields. Verified 2026-10-04: last season actual totals of
# 524 players equal stats.nba.com totals on all 12 fields (a few rows differ by
# stat corrections); projected GP = projected PTS total / PTS average.
STAT_IDS = {
    "42": "gp", "13": "fgm", "14": "fga", "15": "ftm", "16": "fta", "17": "tpm",
    "0": "pts", "6": "reb", "3": "ast", "2": "stl", "1": "blk", "11": "tov",
    "40": "min",  # total minutes: per game it equals the stats.nba.com game log average (521 players)
}
# eligibleSlots ids 0-4 are the real positions. 5-10 are combo slots (G, F, G/F, ...).
SLOT_POSITIONS = {0: "G", 1: "G", 2: "F", 3: "F", 4: "C"}  # PG, SG, SF, PF, C
DEFAULT_POSITION = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}


class EspnPlayers:
    key = "espn"
    label = "ESPN"
    provides = ("ids", "projections", "market")

    def __init__(self, season: str = CURRENT_SEASON):
        self.season = season

    def fetch(self, http: httpx.Client | None = None) -> dict:
        """{"players": <kona_player_info>, "teams": <proTeamSchedules_wl>}"""
        http = http or httpx.Client(timeout=120)
        year = end_year(self.season)
        fltr = {"players": {"limit": LIMIT, "sortDraftRanks": {
            "sortPriority": 100, "sortAsc": True, "value": "STANDARD"}}}
        players = http.get(PLAYERS_URL.format(year=year), params={"view": "kona_player_info"},
                           headers={"x-fantasy-filter": json.dumps(fltr)})
        teams = http.get(BASE.format(year=year), params={"view": "proTeamSchedules_wl"})
        payload = {"players": players.raise_for_status().json(),
                   "teams": teams.raise_for_status().json()}
        save_raw(self.key, payload)
        return payload

    def parse(self, raw: dict, season: str) -> list[SourcePlayer]:
        """Players with a projection (this or last season), a ROTO rank or an average
        auction price. The rest of the feed is deep bench; it would only add unmatched player rows."""
        teams = {t["id"]: canonical(t["abbrev"]) for t in raw["teams"]["settings"]["proTeams"]}
        proj_id, past_id = f"10{end_year(season)}", f"10{end_year(season) - 1}"
        out = []
        for entry in raw["players"]["players"]:
            p = entry["player"]
            proj = next((s for s in p.get("stats", []) if s["id"] == proj_id), None)
            roto = (p.get("draftRanksByRankType") or {}).get("ROTO") or {}
            std = (p.get("draftRanksByRankType") or {}).get("STANDARD") or {}
            own = p.get("ownership") or {}
            past = _stat_line(next((s for s in p.get("stats", []) if s["id"] == past_id), None),
                              previous(season))
            if not (proj or past or roto.get("rank") or own.get("auctionValueAverage")):
                continue
            positions = sorted({SLOT_POSITIONS[s] for s in p.get("eligibleSlots", []) if s in SLOT_POSITIONS},
                               key="GFC".index)
            injury = p.get("injuryStatus")
            out.append(SourcePlayer(
                external_id=str(p["id"]),
                first_name=p["firstName"],
                last_name=p["lastName"],
                team=teams.get(p.get("proTeamId")),
                position=DEFAULT_POSITION.get(p.get("defaultPositionId")),
                projection=_stat_line(proj, season),
                past_projections=[past] if past else [],
                market=MarketValue(
                    season=season,
                    auction_value=roto.get("auctionValue"),
                    average_cost=own.get("auctionValueAverage"),
                    average_pick=own.get("averageDraftPosition"),
                    rank=roto.get("rank"),
                    positions=positions or None,
                    injury=injury if injury and injury != "ACTIVE" else None,
                    extra={k: v for k, v in {
                        "standard_rank": std.get("rank"),
                        "standard_auction_value": std.get("auctionValue"),
                        "percent_owned": own.get("percentOwned"),
                        "percent_started": own.get("percentStarted"),
                        "average_cost_change": own.get("auctionValueAverageChange"),
                        "outlook": p.get("seasonOutlook"),
                    }.items() if v not in (None, "")},
                ),
            ))
        if len(out) < MIN_PLAYERS:
            raise ValueError(f"ESPN {season}: only {len(out)} players")
        return out


def _stat_line(block: dict[str, Any] | None, season: str) -> StatLine | None:
    """ESPN leaves out stat ids whose value is 0."""
    if not block or not block["stats"].get("42"):
        return None
    return StatLine(season=season,
                    stats={field: float(block["stats"].get(sid, 0)) for sid, field in STAT_IDS.items()})
