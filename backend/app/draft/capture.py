"""Capture files written by the Chrome extension feed.

Layout: data/raw/draft_capture/{league_id}/{YYYYMMDD}.jsonl, one folder per
draft. The league id comes from the draft room page URL that the extension
adds to every event. Events from other pages go to `unknown/`.
"""

import gzip
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from app.config import RAW_DIR

CAPTURE_DIR = RAW_DIR / "draft_capture"
UNKNOWN = "unknown"
_PAGE = re.compile(r"/draftclient/nba/(\d+)/(\d+)")


def page_ids(page_url: str | None) -> tuple[str, int] | None:
    """(league_id, my_team_id) from a draft room URL like /draftclient/nba/2600009/5."""
    m = _PAGE.search(page_url or "")
    return (m.group(1), int(m.group(2))) if m else None


def file_for(event: dict, base: Path = CAPTURE_DIR, now: datetime | None = None) -> Path:
    ids = page_ids(event.get("url"))
    folder = base / (ids[0] if ids else UNKNOWN)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{(now or datetime.now(UTC)):%Y%m%d}.jsonl"


def league_ids(base: Path = CAPTURE_DIR) -> list[str]:
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name != UNKNOWN)


def iter_rows(league_id: str, base: Path = CAPTURE_DIR) -> Iterator[dict]:
    """All rows of one draft, in file order (date order). Works on .jsonl and .jsonl.gz."""
    for path in sorted((base / league_id).glob("*.jsonl*")):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def v3_payload(rows: list[dict], resource: str) -> dict | None:
    """Last `fantasy/v3/{resource}` fetch body in the capture, as parsed JSON."""
    found = None
    for row in rows:
        url = row.get("data", {}).get("url", "") if row.get("kind") == "fetch" else ""
        if f"/fantasy/v3/{resource}/" in url:
            try:
                found = json.loads(row["data"]["body"])["service"]
            except (KeyError, ValueError):
                continue
    return found
