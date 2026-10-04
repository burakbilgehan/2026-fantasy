"""stats.nba.com player game logs (`leaguegamelog`, PlayerOrTeam=P).

One request per season returns every player's box score line of every regular
season game (2025-26: 26651 rows, verified 2026-10-04). Games a player did not
play (DNP, inactive) have no row. PLAYER_ID is the NBA person id (source "nba").
Same access rules as nba_stats.py (curl_cffi, Chrome fingerprint, nba.com headers).
Preseason: SeasonType "Pre Season" works the same way (verified 2026-10-04, 31 rows
after the first 2026 preseason game). Only completed seasons have the MIN_ROWS check.

Job: `app/jobs/sync_game_logs.py`.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.sources.players.base import SourcePlayer, save_raw
from app.sources.players.nba_stats import HEADERS
from app.sources.teams import canonical

URL = "https://stats.nba.com/stats/leaguegamelog"
PARAMS = {
    "Counter": "0", "Direction": "ASC", "LeagueID": "00", "PlayerOrTeam": "P",
    "SeasonType": "Regular Season", "Sorter": "DATE", "DateFrom": "", "DateTo": "",
}
MIN_ROWS = 20000  # a full regular season has about 26000 player games
SEASON_TYPES = {"regular": "Regular Season", "preseason": "Pre Season"}
# Our field -> stats.nba.com column.
COLUMNS = {
    "min": "MIN", "fgm": "FGM", "fga": "FGA", "ftm": "FTM", "fta": "FTA", "tpm": "FG3M",
    "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TOV",
}


@dataclass
class GameLine:
    season: str
    game_id: str
    game_date: date
    team: str | None
    opponent: str | None
    home: bool
    stats: dict[str, float]  # keys from COLUMNS


class NbaGameLog:
    key = "nba"

    def fetch(self, seasons: list[str], season_type: str = "regular") -> dict[str, Any]:
        from curl_cffi import requests

        out = {}
        for season in seasons:
            params = {**PARAMS, "Season": season, "SeasonType": SEASON_TYPES[season_type]}
            resp = requests.get(URL, params=params, headers=HEADERS, impersonate="chrome", timeout=120)
            resp.raise_for_status()
            out[season] = resp.json()
            save_raw("nba_gamelog", out[season])
        return out

    def parse(self, raw: dict[str, Any], min_rows: int | None = None) -> list[tuple[SourcePlayer, list[GameLine]]]:
        """raw = {season: response JSON}. One entry per player, games of all seasons.

        min_rows: 0 for a season in progress or for preseason games. Default MIN_ROWS."""
        min_rows = MIN_ROWS if min_rows is None else min_rows
        players: dict[str, tuple[SourcePlayer, list[GameLine]]] = {}
        for season, payload in sorted(raw.items()):
            rs = payload["resultSets"][0]
            if payload["parameters"]["Season"] != season:
                raise ValueError(f"stats.nba.com: asked {season}, got {payload['parameters']['Season']}")
            if len(rs["rowSet"]) < min_rows:
                raise ValueError(f"stats.nba.com game log {season}: only {len(rs['rowSet'])} rows")
            seen = set()
            for row in rs["rowSet"]:
                r = dict(zip(rs["headers"], row))
                pid, gid = str(r["PLAYER_ID"]), str(r["GAME_ID"])
                if (pid, gid) in seen:
                    raise ValueError(f"stats.nba.com game log {season}: player {pid} twice in game {gid}")
                seen.add((pid, gid))
                team = canonical(r["TEAM_ABBREVIATION"])
                if pid not in players:
                    first, _, last = r["PLAYER_NAME"].partition(" ")
                    players[pid] = (SourcePlayer(external_id=pid, first_name=first, last_name=last,
                                                 team=team), [])
                else:  # the latest game wins (seasons sorted, rows by date)
                    players[pid][0].team = team
                # MATCHUP: "GSW vs. LAL" (home) or "GSW @ LAL" (away)
                matchup = r["MATCHUP"]
                players[pid][1].append(GameLine(
                    season=season, game_id=gid, game_date=date.fromisoformat(r["GAME_DATE"]),
                    team=team, opponent=canonical(matchup.split()[-1]), home=" vs. " in matchup,
                    stats={k: float(r[c] or 0) for k, c in COLUMNS.items()},
                ))
        return list(players.values())
