"""stats.nba.com season totals for past seasons (`leaguedashplayerstats`).

PLAYER_ID is the NBA person id, the same id `nba_index` stores as source "nba".
One row per player per season, traded players included (TeamID=0; checked in
parse). Regular season only.

stats.nba.com drops plain httpx and curl requests (Akamai bot protection, timeout).
curl_cffi with a Chrome TLS fingerprint and the nba.com Referer/Origin headers
returns 200 (verified 2026-10-04). If it starts to fail again: try another
`impersonate` target (e.g. "safari"), update curl_cffi, or pull the same URL
once from Chrome on an nba.com page and pass the JSON to parse().

Not in SOURCES: `sync_players.write` creates players and owns identity, which is
wrong for a feed full of retired players. Job: `app/jobs/sync_past_stats.py`.
"""

from typing import Any

from app.sources.players.base import SourcePlayer, StatLine, save_raw
from app.sources.teams import canonical

URL = "https://stats.nba.com/stats/leaguedashplayerstats"
PARAMS = {
    "LastNGames": "0", "LeagueID": "00", "MeasureType": "Base", "Month": "0",
    "OpponentTeamID": "0", "PORound": "0", "PaceAdjust": "N", "PerMode": "Totals",
    "Period": "0", "PlusMinus": "N", "Rank": "N", "SeasonType": "Regular Season", "TeamID": "0",
}
HEADERS = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}
MIN_ROWS = 400  # a full season had 569 to 582 rows (2023-24 to 2025-26)
# Our field -> stats.nba.com column.
COLUMNS = {
    "gp": "GP", "fgm": "FGM", "fga": "FGA", "ftm": "FTM", "fta": "FTA", "tpm": "FG3M",
    "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TOV",
}


class NbaStats:
    key = "nba"
    label = "NBA.com stats"
    provides = ("actual",)

    def fetch(self, seasons: list[str]) -> dict[str, Any]:
        from curl_cffi import requests

        out = {}
        for season in seasons:
            resp = requests.get(URL, params={**PARAMS, "Season": season}, headers=HEADERS,
                                impersonate="chrome", timeout=60)
            resp.raise_for_status()
            out[season] = resp.json()
            save_raw("nba_stats", out[season])
        return out

    def parse(self, raw: dict[str, Any]) -> list[SourcePlayer]:
        """raw = {season: response JSON}. One SourcePlayer per player, one StatLine per season."""
        players: dict[str, SourcePlayer] = {}
        for season, payload in sorted(raw.items()):
            rs = payload["resultSets"][0]
            if payload["parameters"]["Season"] != season:
                raise ValueError(f"stats.nba.com: asked {season}, got {payload['parameters']['Season']}")
            if len(rs["rowSet"]) < MIN_ROWS:
                raise ValueError(f"stats.nba.com {season}: only {len(rs['rowSet'])} rows")
            ids = [row[rs["headers"].index("PLAYER_ID")] for row in rs["rowSet"]]
            if len(ids) != len(set(ids)):
                raise ValueError(f"stats.nba.com {season}: a player has more than one row")
            for row in rs["rowSet"]:
                r = dict(zip(rs["headers"], row))
                pid = str(r["PLAYER_ID"])
                if pid not in players:
                    first, _, last = r["PLAYER_NAME"].partition(" ")
                    players[pid] = SourcePlayer(
                        external_id=pid, first_name=first, last_name=last,
                        team=canonical(r.get("TEAM_ABBREVIATION")),
                    )
                else:  # the latest season wins (sorted order)
                    players[pid].team = canonical(r.get("TEAM_ABBREVIATION"))
                players[pid].actual.append(StatLine(
                    season=season, stats={k: float(r[c]) for k, c in COLUMNS.items()}))
        return list(players.values())
