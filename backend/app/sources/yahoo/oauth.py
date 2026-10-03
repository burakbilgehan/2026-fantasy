"""Yahoo OAuth 2.0 (authorization code grant), read scope only.

Refresh does not need redirect_uri (verified against Yahoo on 2026-10-03).
"""

import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
SCOPE = "fspt-r"
# Refresh a bit before the real expiry.
EXPIRY_MARGIN_S = 120


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text())

    def save(self, token: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(token, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)


class YahooOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, store: TokenStore,
                 http: httpx.Client | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.store = store
        self.http = http or httpx.Client(timeout=20)

    def authorize_url(self) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
        }
        return f"{AUTH_URL}?{urlencode(query)}"

    def exchange_code(self, code_or_url: str) -> dict:
        """Accept the bare code or the full redirected URL."""
        code = code_or_url.strip()
        if code.startswith("http"):
            params = parse_qs(urlparse(code).query)
            if "error" in params:
                raise RuntimeError(f"Yahoo auth error: {params['error'][0]}")
            code = params["code"][0]
        return self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri}
        )

    def refresh(self, refresh_token: str) -> dict:
        return self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def access_token(self) -> str:
        token = self.store.load()
        if token is None:
            raise RuntimeError("No Yahoo token. Run: make yahoo-auth")
        # Tokens without obtained_at are treated as expired.
        expires_at = token.get("obtained_at", 0) + token.get("expires_in", 0) - EXPIRY_MARGIN_S
        if time.time() >= expires_at:
            token = self.refresh(token["refresh_token"])
        return token["access_token"]

    def _token_request(self, data: dict) -> dict:
        resp = self.http.post(TOKEN_URL, data=data, auth=(self.client_id, self.client_secret))
        if resp.status_code != 200:
            raise RuntimeError(f"Yahoo token request failed ({resp.status_code}): {resp.text[:300]}")
        token = resp.json()
        previous = self.store.load() or {}
        # Keep the old refresh token if Yahoo does not send a new one.
        token.setdefault("refresh_token", previous.get("refresh_token"))
        token["obtained_at"] = int(time.time())
        self.store.save(token)
        return token
