"""Fantrax ADP (average draft position over all Fantrax leagues).

URLs (Fantrax public "fxea" API, no login, verified 2026-10-05):
- www.fantrax.com/fxea/general/getAdp?sport=NBA: about 330 players, sorted by ADP.
  Per player: Fantrax id, "Last, First" name, one primary position, ADP.
  `limit` is ignored (330 with limit=1000).
- www.fantrax.com/fxea/general/getPlayerIds?sport=NBA: every Fantrax NBA player id
  with team (Fantrax abbreviations, "(N/A)" = no team), primary position,
  Rotowire and Sportradar ids. Used for the team (linking by name + team).
Raw copies in data/raw/fantrax/.

Projections (2026-10-05): only on a league's players page (fxpa/req `getPlayerStats`), and
only with a login. The fixed script `fantrax_capture.js` (next to this file), run in the user's
logged-in Fantrax tab (Claude in Chrome, javascript tool), reads
every page of a public league's players list (view "Projected - Season", scoring category
type 1 = Standard: GP, MIN, FGM, FGA, FG%, FTM, FTA, FT%, 3PTM, REB, AST, ST, BLK, TO, PTS,
all per game) and posts the rows to `POST /api/capture/fantrax-projections`, which saves
them to data/raw/fantrax_projections/. No Fantrax password or cookie reaches this code.
`fetch` adds the newest such file when it is at most PROJECTION_MAX_AGE_DAYS old.
Verified: Luka Doncic 2 x 11.1 + 6.5 + 3.9 = 32.6 vs PTS 32.7 (rounding of per-game values).
"""

import json
import time

import httpx

from app.config import RAW_DIR
from app.sources.players.base import MarketValue, SourcePlayer, StatLine, save_raw
from app.sources.teams import canonical

BASE = "https://www.fantrax.com/fxea/general"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) 2026-fantasy personal read-only"
MIN_PLAYERS = 200  # the sync replaces all fantrax rows: never write a short response
PROJECTION_DIR = RAW_DIR / "fantrax_projections"
PROJECTION_MAX_AGE_DAYS = 14
MIN_PROJECTIONS = 300
# Fantrax header -> per-game field. Makes come from the percentage x attempts (3 decimals),
# which is closer than the rounded per-game makes.
PROJ_COLUMNS = {"GP": "gp", "MIN": "min", "FGA": "fga", "FG%": "fg_pct", "FTA": "fta", "FT%": "ft_pct",
                "3PTM": "tpm", "REB": "reb", "AST": "ast", "ST": "stl", "BLK": "blk", "TO": "tov", "PTS": "pts"}


def newest_projections() -> dict | None:
    files = sorted(PROJECTION_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime) if PROJECTION_DIR.exists() else []
    if not files or time.time() - files[-1].stat().st_mtime > PROJECTION_MAX_AGE_DAYS * 86400:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def projection_line(header: list[str], cells: list[str], season: str) -> StatLine | None:
    """Season totals from Fantrax per-game cells. None when the player has no games."""
    row = dict(zip(header, cells))

    def num(k: str) -> float:
        v = (row.get(k) or "").strip()
        return float(v) if v not in ("", "-") else 0.0

    pg = {f: num(k) for k, f in PROJ_COLUMNS.items()}
    gp = pg.pop("gp")
    if gp <= 0:
        return None
    fg, ft = pg.pop("fg_pct"), pg.pop("ft_pct")
    tot = {k: v * gp for k, v in pg.items()}
    tot["fgm"], tot["ftm"], tot["gp"] = fg * tot["fga"], ft * tot["fta"], gp
    return StatLine(season=season, stats=tot)


def split_name(name: str) -> tuple[str, str]:
    """'Oubre Jr., Kelly' -> ('Kelly', 'Oubre Jr.'). A name without a comma is all first name."""
    last, sep, first = name.partition(", ")
    return (first.strip(), last.strip()) if sep else (name.strip(), "")


class FantraxPlayers:
    key = "fantrax"
    label = "Fantrax"
    provides = ("ids", "market", "projection")

    def fetch(self, http: httpx.Client | None = None) -> dict:
        """{"adp": <getAdp list>, "ids": <getPlayerIds dict>}"""
        http = http or httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})
        adp = http.get(f"{BASE}/getAdp", params={"sport": "NBA"})
        ids = http.get(f"{BASE}/getPlayerIds", params={"sport": "NBA"})
        payload = {"adp": adp.raise_for_status().json(), "ids": ids.raise_for_status().json()}
        save_raw(self.key, payload)
        payload["projections"] = newest_projections()  # already saved raw by the capture endpoint
        return payload

    def parse(self, raw: dict, season: str) -> list[SourcePlayer]:
        """Players in the ADP list only. The id list alone has no value data, so it only
        gives the team."""
        ids = raw["ids"]
        out = []
        for row in raw["adp"]:
            info = ids.get(row["id"]) or {}
            first, last = split_name(row["name"])
            out.append(SourcePlayer(
                external_id=row["id"],
                first_name=first,
                last_name=last,
                team=canonical(info.get("team")),
                position=row.get("pos") or info.get("position"),
                market=MarketValue(
                    season=season,
                    average_pick=row.get("ADP"),
                    # `pos` is one primary position, not eligibility: positions stays None.
                    extra={k: v for k, v in {
                        "primary_pos": row.get("pos"),
                        "rotowire_id": info.get("rotowireId"),
                        "sportradar_id": info.get("sportRadarId"),
                    }.items() if v not in (None, "")},
                ),
            ))
        if len(out) < MIN_PLAYERS:
            raise ValueError(f"Fantrax ADP: only {len(out)} players")
        proj = raw.get("projections")
        if proj:
            if len(proj["rows"]) < MIN_PROJECTIONS:
                raise ValueError(f"Fantrax projections: only {len(proj['rows'])} rows")
            by_id = {sp.external_id: sp for sp in out}
            for r in proj["rows"]:
                line = projection_line(proj["header"], r["cells"], season)
                if line is None:
                    continue
                sp = by_id.get(r["id"])
                if sp is None:  # projected but not in the ADP list
                    first, _, last = r["name"].partition(" ")
                    info = ids.get(r["id"]) or {}
                    sp = SourcePlayer(external_id=r["id"], first_name=first, last_name=last,
                                      team=canonical(info.get("team") or r.get("team")))
                    by_id[r["id"]] = sp
                    out.append(sp)
                sp.projection = line
        return out
