"""stats.nba.com advanced season stats (`leaguedashplayerstats`, MeasureType=Advanced).

Same endpoint and access as `nba_stats.py` (curl_cffi, Chrome fingerprint). Gives usage
rate (USG_PCT), true shooting and more, per player per season (verified 2026-10-05:
2025-26 has 582 rows; Jokić USG_PCT 0.289). Rate columns are fractions. MIN is per game
even with PerMode=Totals. Regular season only.
"""

import time
from typing import Any

from app.sources.players.base import save_raw
from app.sources.players.nba_stats import HEADERS, MIN_ROWS, PARAMS, URL

KEEP = ("AGE", "MIN", "AST_PCT", "AST_TO", "AST_RATIO", "OREB_PCT", "DREB_PCT", "REB_PCT", "TM_TOV_PCT",
        "EFG_PCT", "TS_PCT", "USG_PCT", "E_USG_PCT", "PACE", "PIE", "POSS", "OFF_RATING", "DEF_RATING",
        "NET_RATING")


def fetch(seasons: list[str]) -> dict[str, Any]:
    from curl_cffi import requests

    out = {}
    for season in seasons:
        # stats.nba.com sometimes answers 500 or an empty body to quick repeat calls: wait and retry.
        for attempt in range(4):
            resp = requests.get(URL, params={**PARAMS, "MeasureType": "Advanced", "Season": season},
                                headers=HEADERS, impersonate="chrome", timeout=60)
            if resp.status_code == 200 and resp.text.startswith("{"):
                break
            time.sleep(5 * (attempt + 1))
        resp.raise_for_status()
        out[season] = resp.json()
        save_raw("nba_advanced", out[season])
    return out


def parse(raw: dict[str, Any]) -> list[dict]:
    """raw = {season: response JSON}. One dict per player per season: nba_id, season, gp, usg_pct, ts_pct, extra."""
    rows = []
    for season, payload in sorted(raw.items()):
        if payload["parameters"]["Season"] != season or payload["parameters"]["MeasureType"] != "Advanced":
            raise ValueError(f"stats.nba.com advanced: asked {season}, got {payload['parameters']}")
        rs = payload["resultSets"][0]
        if len(rs["rowSet"]) < MIN_ROWS:
            raise ValueError(f"stats.nba.com advanced {season}: only {len(rs['rowSet'])} rows")
        for row in rs["rowSet"]:
            r = dict(zip(rs["headers"], row))
            rows.append({"nba_id": str(r["PLAYER_ID"]), "name": r["PLAYER_NAME"], "season": season,
                         "gp": float(r["GP"]), "usg_pct": r.get("USG_PCT"), "ts_pct": r.get("TS_PCT"),
                         "extra": {k.lower(): r.get(k) for k in KEEP}})
    return rows
