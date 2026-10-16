"""NBA.com player index: NBA person ids for every player on a current roster.

Read from the `__NEXT_DATA__` JSON of https://www.nba.com/players (verified
2026-10-04, 620 players). cdn.nba.com JSON is blocked from this machine (403,
verified 2026-10-04). Since 2026-10-07 the page also refuses plain httpx (403),
so it is fetched with curl_cffi and a browser TLS fingerprint (Chrome verified
2026-10-11, 622 players; on 2026-10-16 Chrome got 403 and Safari 200, so the
fingerprints are tried in order). stats.nba.com opens only with curl_cffi too (see nba_stats.py)
and has no roster list, so this page is the id source.
Free agents are not on the page. Raw copies in data/raw/nba/.
"""

import json
import re

from app.sources.players.base import SourcePlayer, save_raw
from app.sources.teams import canonical

URL = "https://www.nba.com/players"
IMPERSONATE = ("chrome", "safari")  # first that is not refused (403)
MIN_PLAYERS = 300  # 30 rosters; the page had 620 on 2026-10-04
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class NbaIndex:
    key = "nba"
    label = "NBA.com"
    provides = ("ids",)

    def fetch(self) -> str:
        from curl_cffi import requests

        for imp in IMPERSONATE:
            resp = requests.get(URL, impersonate=imp, timeout=60)
            if resp.status_code != 403:
                break
        resp.raise_for_status()
        save_raw(self.key, resp.text, suffix="html")
        return resp.text

    def parse(self, raw: str, season: str) -> list[SourcePlayer]:
        m = _NEXT_DATA.search(raw)
        if not m:
            raise ValueError("nba.com/players: no __NEXT_DATA__ block")
        rows = json.loads(m.group(1))["props"]["pageProps"]["players"]
        if len(rows) < MIN_PLAYERS:  # a broken page must not mark everyone a free agent
            raise ValueError(f"nba.com/players: only {len(rows)} players")
        return [
            SourcePlayer(
                external_id=str(r["PERSON_ID"]),
                first_name=r["PLAYER_FIRST_NAME"],
                last_name=r["PLAYER_LAST_NAME"],
                team=canonical(r.get("TEAM_ABBREVIATION")),
                position=r.get("POSITION") or None,
            )
            for r in rows
        ]
