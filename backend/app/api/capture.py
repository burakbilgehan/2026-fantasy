"""Capture sink for the Chrome extension.

The extension sends what the Yahoo draft room receives (network payloads and
DOM snapshots). Events are stored as JSON lines, one folder per draft
(see app.draft.capture). Parsing happens later, on replay.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.draft import capture as store

router = APIRouter(prefix="/api/capture")


@router.post("")
async def capture(request: Request) -> dict:
    event = await request.json()
    now = datetime.now(UTC)
    event["received_at"] = now.isoformat()
    with store.file_for(event, store.CAPTURE_DIR, now).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True}


@router.get("/stats")
def stats() -> dict:
    """Today's capture files: event count and kinds per folder."""
    day = f"{datetime.now(UTC):%Y%m%d}.jsonl"
    out = {}
    for path in sorted(store.CAPTURE_DIR.glob(f"*/{day}")):
        kinds: dict[str, int] = {}
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            kind = json.loads(line).get("kind", "?")
            kinds[kind] = kinds.get(kind, 0) + 1
        out[path.parent.name] = {"file": str(path), "events": len(lines), "kinds": kinds}
    return out
