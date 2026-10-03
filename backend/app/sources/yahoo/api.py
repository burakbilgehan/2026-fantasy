"""Read-only Yahoo Fantasy API client. GET requests only.

Since 2026-07 Yahoo gates the Fantasy API behind a separate approval
(https://sports.yahoo.com/developer/access/). Unapproved apps get 403
"This application is not authorized to perform this action." on every endpoint.
"""

import httpx

from app.sources.yahoo.oauth import YahooOAuth

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


class YahooAccessDenied(RuntimeError):
    """The app has a valid token but no Fantasy API approval."""


class YahooApiClient:
    def __init__(self, oauth: YahooOAuth, http: httpx.Client | None = None):
        self.oauth = oauth
        self.http = http or httpx.Client(timeout=20)

    def get(self, path: str) -> dict:
        resp = self.http.get(
            f"{BASE_URL}/{path.lstrip('/')}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {self.oauth.access_token()}"},
        )
        if resp.status_code in (401, 403) and "not authorized" in resp.text:
            raise YahooAccessDenied(resp.json().get("error", {}).get("description", resp.text))
        resp.raise_for_status()
        return resp.json()

    def league_settings(self, league_key: str) -> dict:
        return self.get(f"league/{league_key}/settings")

    def league_teams(self, league_key: str) -> dict:
        return self.get(f"league/{league_key}/teams")

    def league_draftresults(self, league_key: str) -> dict:
        return self.get(f"league/{league_key}/draftresults")


# NOT VERIFIED: the two parsers below follow the documented JSON shape.
# Check them against a real response once Yahoo approves API access.
def parse_settings(payload: dict) -> dict:
    """Normalize league/{key}/settings JSON to the same shape as web.parse_settings."""
    meta, settings_block = payload["fantasy_content"]["league"][:2]
    s = settings_block["settings"][0]
    roster = []
    for item in s["roster_positions"]:
        pos = item["roster_position"]
        roster += [pos["position"]] * int(pos["count"])
    cats = [
        c["stat"]["display_name"]
        for c in s["stat_categories"]["stats"]
        if not c["stat"].get("is_only_display_stat")
    ]
    return {
        "name": meta["name"],
        "num_teams": int(meta["num_teams"]),
        "scoring_type": meta["scoring_type"],
        "draft_type": s.get("draft_type", ""),
        "draft_budget": None,
        "draft_time": None,
        "roster_positions": roster,
        "stat_categories": cats,
        "raw": s,
    }


def parse_teams(payload: dict) -> list[dict]:
    teams_block = payload["fantasy_content"]["league"][1]["teams"]
    out = []
    for key, value in teams_block.items():
        if key == "count":
            continue
        fields = {k: v for d in value["team"][0] if isinstance(d, dict) for k, v in d.items()}
        out.append({"team_id": int(fields["team_id"]), "name": fields["name"]})
    return sorted(out, key=lambda t: t["team_id"])
