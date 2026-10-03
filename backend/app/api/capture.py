"""Raw capture sink for the Chrome extension (discovery phase).

The extension sends what the Yahoo draft room receives (network payloads and
DOM snapshots). We store everything as JSON lines and decide the parser later.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.config import RAW_DIR

router = APIRouter(prefix="/api/capture")
CAPTURE_DIR = RAW_DIR / "draft_capture"


def _file():
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    return CAPTURE_DIR / f"{datetime.now(UTC):%Y%m%d}.jsonl"


@router.post("")
async def capture(request: Request) -> dict:
    event = await request.json()
    event["received_at"] = datetime.now(UTC).isoformat()
    with _file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True}


@router.get("/stats")
def stats() -> dict:
    path = _file()
    if not path.exists():
        return {"file": str(path), "events": 0, "kinds": {}}
    kinds: dict[str, int] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        kind = json.loads(line).get("kind", "?")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"file": str(path), "events": len(lines), "kinds": kinds}
