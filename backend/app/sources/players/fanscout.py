"""FanScout projections (https://fanscout.pro), free, 2026-27.

Pages are Next.js app router: the data is in `self.__next_f.push([1,"..."])` flight
chunks (concatenate, JSON-unescape each string). Verified 2026-10-05:
- Team depth chart pages `/nba-depth-charts/{team-slug}` (30, listed in `/sitemap.xml`)
  embed `{"data":[...]}`: one row per rostered player with `playerId` (NBA person id),
  `playerName`, `playerSlug`, `team` (NBA abbreviation) and a `projections` object.
- `projections` = per game: `gamesPlayed`, `totalMinutes` (minutes PER GAME despite the
  name), pts, tpm, ast, reb, stl, blk, tov, fgP, fga, ftP, fta, plus z-scores. No FGM/FTM.
- It is the 2026-27 projection: 2026 rookies have one (AJ Dybantsa 73 GP), players traded
  in summer 2026 sit on the new team, Tyrese Haliburton (no 2025-26 game) has 61 GP.
- Player pages `/{slug}-fantasy-stats` hold the same object, but rookie pages have none
  and the NBA id there is only in game log rows. So this source reads the 30 team pages.
  Free agents (not on a roster page) are not covered.
- Page titles say "2025-26"; `/fantasy-basketball-player-rankings-and-projections` holds
  2025-26 actuals, not projections.
robots.txt allows these pages. Polite: one request per second, stop on the first error.
"""

import json
import re
import time

import httpx

from app.sources.players.base import SourcePlayer, StatLine, save_raw
from app.sources.teams import canonical

BASE = "https://fanscout.pro"
SITEMAP = f"{BASE}/sitemap.xml"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 2026-fantasy personal read-only"
PAUSE = 1.0  # seconds between requests
TEAM_PAGES = 30
MIN_PROJECTIONS = 200  # the sync replaces all fanscout rows: never write a short response

_TEAM_URL = re.compile(r"<loc>(https://fanscout\.pro/nba-depth-charts/[a-z0-9-]+)</loc>")
_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_DATA = re.compile(r'\{"data":\[\{"gamesPlayed"')
PER_GAME = ("pts", "tpm", "ast", "reb", "stl", "blk", "tov", "fga", "fta")


def team_urls(sitemap: str) -> list[str]:
    urls = sorted(set(_TEAM_URL.findall(sitemap)))
    if len(urls) != TEAM_PAGES:
        raise ValueError(f"FanScout sitemap: {len(urls)} team depth chart pages, expected {TEAM_PAGES}")
    return urls


def flight(html: str) -> str:
    """The React flight payload of a Next.js app router page, as one string."""
    return "".join(json.loads(f'"{s}"') for s in _CHUNK.findall(html))


def team_rows(html: str) -> list[dict]:
    """The player rows of one team depth chart page."""
    t = flight(html)
    m = _DATA.search(t)
    if m is None:
        raise ValueError("FanScout: no player data in the team page")
    return json.JSONDecoder().raw_decode(t, m.start())[0]["data"]


def compact(row: dict) -> dict:
    """The fields we use, for the raw copy."""
    p = row.get("projections") or {}
    return {"playerId": row.get("playerId"), "playerName": row.get("playerName"),
            "playerSlug": row.get("playerSlug"), "team": row.get("team"),
            "projections": {k: p.get(k) for k in ("gamesPlayed", "totalMinutes", "fgP", "ftP", *PER_GAME)}}


def projection_line(p: dict, season: str) -> StatLine | None:
    """Season totals from FanScout per-game values. None when no games are projected."""
    gp = float(p.get("gamesPlayed") or 0)
    if gp <= 0:
        return None
    tot = {k: float(p.get(k) or 0) * gp for k in PER_GAME}
    tot["fgm"] = float(p.get("fgP") or 0) * tot["fga"]
    tot["ftm"] = float(p.get("ftP") or 0) * tot["fta"]
    tot["min"] = float(p.get("totalMinutes") or 0) * gp
    tot["gp"] = gp
    return StatLine(season=season, stats=tot)


class FanScoutPlayers:
    key = "fanscout"
    label = "FanScout"
    provides = ("projections",)

    def fetch(self, http: httpx.Client | None = None, pause: float = PAUSE) -> dict:
        """{"rows": [compact row, ...]} from the 30 team pages, in sitemap order."""
        http = http or httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        urls = team_urls(http.get(SITEMAP).raise_for_status().text)
        rows = []
        for url in urls:
            time.sleep(pause)
            rows += [compact(r) for r in team_rows(http.get(url).raise_for_status().text)]
        payload = {"pages": len(urls), "rows": rows}
        save_raw(self.key, payload)
        return payload

    def parse(self, raw: dict, season: str) -> list[SourcePlayer]:
        """Players with projected games. One row per NBA id (a player on two pages: first wins).
        External id = NBA person id; it is also passed as an alias of source "nba"."""
        out, seen = [], set()
        for r in raw["rows"]:
            line = projection_line(r.get("projections") or {}, season)
            nba_id = str(r.get("playerId") or "")
            if line is None or not nba_id or nba_id in seen:
                continue
            seen.add(nba_id)
            first, _, last = (r.get("playerName") or "").strip().partition(" ")
            out.append(SourcePlayer(external_id=nba_id, first_name=first, last_name=last,
                                    team=canonical(r.get("team")), projection=line,
                                    aliases=[("nba", nba_id)]))
        if len(out) < MIN_PROJECTIONS:
            raise ValueError(f"FanScout: only {len(out)} projections")
        return out
