"""Yahoo player feed loaded by the Yahoo draft client.

URL: pub-api.fantasysports.yahoo.com/fantasy/v3/players/nba/{league_id}
Public, no login, no OAuth app approval (verified 2026-10-04, league 23772).
Undocumented: sync on demand only, never on a timer. Raw copies in data/raw/yahoo/.

Per player: projected_stats (season being drafted), season_stats (previous
season), Yahoo auction value, average auction cost, ranks, eligible positions.
"""

from typing import Any

import httpx

from app.config import get_settings
from app.seasons import previous
from app.sources.players.base import MarketValue, SourcePlayer, StatLine, save_raw
from app.sources.teams import canonical

URL = "https://pub-api.fantasysports.yahoo.com/fantasy/v3/players/nba/{league_id}"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 2026-fantasy personal read-only"

# Yahoo stat ids -> our fields. Ids 0, 3, 4, 6, 7, 10, 12 are verified by
# arithmetic on all 707 players (PTS = 2*FGM + FTM + 3PM, FG% = FGM/FGA,
# FT% = FTM/FTA). Ids 15 to 19 follow Yahoo's stat id list (inferred).
STAT_IDS = {
    "0": "gp", "3": "fga", "4": "fgm", "6": "fta", "7": "ftm", "10": "tpm",
    "12": "pts", "15": "reb", "16": "ast", "17": "stl", "18": "blk", "19": "tov",
}


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # Yahoo sends "-" when there are no stats


def _stat_line(raw: dict | None, season: str) -> StatLine | None:
    stats = {field: _num((raw or {}).get(sid)) for sid, field in STAT_IDS.items()}
    if any(v is None for v in stats.values()) or not stats["gp"]:
        return None
    return StatLine(season=season, stats=stats)


class YahooPlayers:
    key = "yahoo"
    label = "Yahoo"
    provides = ("ids", "projections", "actual", "market")

    def __init__(self, league_id: str | None = None):
        self.league_id = league_id or get_settings().yahoo_league_id

    def fetch(self, http: httpx.Client | None = None) -> dict:
        http = http or httpx.Client(timeout=60)
        resp = http.get(
            URL.format(league_id=self.league_id),
            params={"projected": 1, "average": 1, "format": "rawjson"},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        payload = resp.json()
        save_raw(self.key, payload)
        return payload

    def parse(self, raw: dict, season: str) -> list[SourcePlayer]:
        out = []
        for p in raw["service"]["player_list"]:
            actual = _stat_line(p.get("season_stats"), previous(season))
            out.append(SourcePlayer(
                external_id=str(p["id"]),
                first_name=p["fname"],
                last_name=p["lname"],
                team=canonical(p.get("team_abbr")),
                position=p.get("primary_pos"),
                projection=_stat_line(p.get("projected_stats"), season),
                actual=[actual] if actual else [],
                market=MarketValue(
                    season=season,
                    auction_value=_num(p.get("auction-value")),
                    average_cost=_num(p.get("average-cost")),
                    average_pick=_num(p.get("average-pick")),
                    percent_drafted=_num(p.get("percent-drafted")),
                    rank=p.get("o_rank"),
                    positions=[x for x in p.get("pos", []) if x != "Util"],
                    injury=p.get("inj") or None,
                    injury_note=p.get("inj_note") or None,
                    extra={k: p.get(k) for k in (
                        "psr_rank", "s_rank_1", "avg_rank_1", "preseason-average-cost",
                        "preseason-average-pick", "inj_full", "player_key",
                    ) if p.get(k) not in (None, "")},
                ),
            ))
        return out
