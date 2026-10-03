"""Yahoo auth helper.

  uv run python -m app.sources.yahoo.cli auth    # one-time login, paste the redirected URL
  uv run python -m app.sources.yahoo.cli check   # refresh token and test one API call
"""

import sys
import webbrowser

from app.config import get_settings
from app.sources.yahoo.api import YahooAccessDenied
from app.sources.yahoo.factory import make_api_client, make_oauth


def auth() -> None:
    oauth = make_oauth()
    url = oauth.authorize_url()
    print("Open this URL, click Agree, then copy the URL of the page you land on.")
    print("(The localhost page will fail to load. That is expected.)\n")
    print(url, "\n")
    webbrowser.open(url)
    oauth.exchange_code(input("Paste the redirected URL or the code: "))
    print("Token saved.")


def check() -> None:
    client = make_api_client()
    key = f"nba.l.{get_settings().yahoo_league_id}"
    try:
        data = client.league_settings(key)
        print("API OK:", data["fantasy_content"]["league"][0]["name"])
    except YahooAccessDenied as exc:
        print("Token OK, but the Fantasy API is not approved for this app:", exc)
        print("Apply at https://sports.yahoo.com/developer/access/")
        sys.exit(2)


if __name__ == "__main__":
    {"auth": auth, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "check"]()
