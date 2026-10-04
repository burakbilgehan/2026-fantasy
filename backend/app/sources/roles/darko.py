"""DARKO projections (https://www.darko.app/projections, "Fantasy Lab").

The page embeds every player in the SvelteKit start script as a JS object
literal: `data:{players:[{nba_id:203999,player_name:"Nikola Jokic",...,
x_minutes:31.6619,x_pace:95.08,x_pts_100:31.2113,...}],asOf:"2026-07-26"}`.
Keys are unquoted and floats can start with a dot (`.534094`), so the literal is
rewritten into JSON before loading. Rates are per 100 possessions; `x_minutes`
is minutes per game. No games played. `date` = last update of the player row.
`x_minutes` can be below 0 for fringe players (minimum -9.9 on 2026-10-04): stored
as 0, the raw value stays in `extra`.
Per the About page, DARKO has no preseason data and minutes are its weakest stat.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from app.sources.players.base import save_raw
from app.sources.roles import get
from app.sources.teams import from_full_name

KEY = "darko"
URL = "https://www.darko.app/projections"
MIN_PLAYERS = 400  # 530 on 2026-10-04

_KEY = re.compile(r'([{,])([A-Za-z_]\w*):')
_DOT_FLOAT = re.compile(r'([:\[,])(-?)\.(\d)')


@dataclass
class DarkoPlayer:
    nba_id: str
    name: str
    team: str | None
    mpg: float
    extra: dict[str, Any]  # every other field of the row, as DARKO gives it


def fetch() -> str:
    html = get(URL)
    save_raw(KEY, html, suffix="html")
    return html


def _players_literal(html: str) -> str:
    start = html.find("players:[")
    if start < 0:
        raise ValueError("DARKO: no players array in the page")
    i = start + len("players:")
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "[":
            depth += 1
        elif html[j] == "]":
            depth -= 1
            if depth == 0:
                return html[i:j + 1]
    raise ValueError("DARKO: players array not closed")


def to_json(literal: str) -> str:
    """JS object literal -> JSON. Only the forms DARKO uses: unquoted keys, .5 floats, void 0."""
    s = _KEY.sub(r'\1"\2":', literal)
    s = _DOT_FLOAT.sub(r'\1\g<2>0.\3', s)
    return s.replace("void 0", "null")


def parse(html: str) -> list[DarkoPlayer]:
    literal = _players_literal(html)
    rows = json.loads(to_json(literal))
    if len(rows) != literal.count("nba_id:"):
        raise ValueError("DARKO: parsed row count differs from the page")
    if len(rows) < MIN_PLAYERS:
        raise ValueError(f"DARKO: only {len(rows)} players")
    out = []
    for r in rows:
        mpg = r.get("x_minutes")
        if mpg is None:
            continue
        if not isinstance(mpg, (int, float)):
            raise ValueError(f"DARKO: x_minutes is not a number for {r.get('player_name')}")
        extra = {k: v for k, v in r.items() if k not in ("nba_id", "player_name")}
        out.append(DarkoPlayer(nba_id=str(r["nba_id"]), name=r["player_name"],
                               team=from_full_name(r.get("team_name")), mpg=max(0.0, float(mpg)),
                               extra=extra))
    return out
