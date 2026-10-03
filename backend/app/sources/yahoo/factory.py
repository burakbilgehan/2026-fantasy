from app.config import get_settings
from app.sources.yahoo.api import YahooApiClient
from app.sources.yahoo.oauth import TokenStore, YahooOAuth


def make_oauth() -> YahooOAuth:
    s = get_settings()
    return YahooOAuth(s.yahoo_client_id, s.yahoo_client_secret, s.yahoo_redirect_uri,
                      TokenStore(s.token_path))


def make_api_client() -> YahooApiClient:
    return YahooApiClient(make_oauth())
