"""Capture sink for the Chrome extension.

The extension sends what the Yahoo draft room receives (network payloads and
DOM snapshots). Events are stored as JSON lines, one folder per draft
(see app.draft.capture), then applied to the live draft state (app.draft.live).
Each sale also rewrites the draft's rows in the DB, in the background.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Request

from app.draft import capture as store
from app.draft import live
from app.jobs import ingest_draft

router = APIRouter(prefix="/api/capture")


@router.post("")
async def capture(request: Request, background: BackgroundTasks) -> dict:
    event = await request.json()
    now = datetime.now(UTC)
    event["received_at"] = now.isoformat()
    # One lock for write + feed: a first-use rebuild in between would apply this row twice.
    with live.lock:
        with store.file_for(event, store.CAPTURE_DIR, now).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        league_id = live.feed(event)
    if league_id:
        background.add_task(ingest_draft.ingest_now, league_id, store.CAPTURE_DIR)
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
