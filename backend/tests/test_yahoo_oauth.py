import time

import httpx
import pytest
import respx

from app.sources.yahoo.api import YahooAccessDenied, YahooApiClient
from app.sources.yahoo.oauth import TOKEN_URL, TokenStore, YahooOAuth


@pytest.fixture
def oauth(tmp_path):
    return YahooOAuth("cid", "secret", "https://localhost:8000/cb", TokenStore(tmp_path / "t.json"))


def test_authorize_url_uses_read_scope(oauth):
    url = oauth.authorize_url()
    assert "scope=fspt-r" in url
    assert "response_type=code" in url


@respx.mock
def test_exchange_code_from_redirect_url(oauth):
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}))
    oauth.exchange_code("https://localhost:8000/cb?code=abc123")
    assert b"code=abc123" in route.calls[0].request.content
    saved = oauth.store.load()
    assert saved["access_token"] == "a1"
    assert saved["obtained_at"] <= time.time()


def test_exchange_code_raises_on_error_url(oauth):
    with pytest.raises(RuntimeError, match="invalid_scope"):
        oauth.exchange_code("https://localhost:8000/cb?error=invalid_scope")


@respx.mock
def test_expired_token_is_refreshed_and_keeps_refresh_token(oauth):
    oauth.store.save({"access_token": "old", "refresh_token": "r1", "expires_in": 3600,
                      "obtained_at": int(time.time()) - 4000})
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "new", "expires_in": 3600}))
    assert oauth.access_token() == "new"
    assert b"grant_type=refresh_token" in route.calls[0].request.content
    assert oauth.store.load()["refresh_token"] == "r1"


def test_fresh_token_is_not_refreshed(oauth):
    oauth.store.save({"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                      "obtained_at": int(time.time())})
    assert oauth.access_token() == "a"


@respx.mock
def test_api_403_raises_access_denied(oauth):
    oauth.store.save({"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                      "obtained_at": int(time.time())})
    respx.get(url__startswith="https://fantasysports.yahooapis.com").mock(return_value=httpx.Response(
        403, json={"error": {"description": "This application is not authorized to perform this action."}}))
    with pytest.raises(YahooAccessDenied):
        YahooApiClient(oauth).league_settings("nba.l.23772")
