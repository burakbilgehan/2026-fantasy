"""Role sources (T-026): projected minutes, depth charts, team win totals.

Each module has `fetch()` (download, save the raw copy) and a pure `parse()`.
Sources never touch the DB. Job: `app/jobs/sync_roles.py`. Source rows and terms:
`docs/DATA_SOURCES.md`.
"""

from curl_cffi import requests

TIMEOUT = 60


def get(url: str) -> str:
    """GET with a Chrome TLS fingerprint. DARKO and the Vegas page need it (verified 2026-10-04)."""
    resp = requests.get(url, impersonate="chrome", timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text
