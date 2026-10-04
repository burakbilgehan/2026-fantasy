import threading
from datetime import UTC, datetime

from fastapi import APIRouter

from app.db import SessionLocal
from app.jobs import refresh

router = APIRouter(prefix="/api/sync")


def _iso(t: datetime | None) -> str | None:
    return t.replace(tzinfo=UTC).isoformat() if t else None


@router.get("/status")
def get_status() -> list[dict]:
    """Per refresh job: last run, last success, TTL, and whether it is stale now."""
    now = datetime.now(UTC)
    with SessionLocal() as db:
        state = refresh.last_runs(db)
    out = []
    for name, job in refresh.JOBS.items():
        last, ok = state[name]["last"], state[name]["last_ok"]
        out.append({
            "job": name, "ttl_hours": job.ttl.total_seconds() / 3600,
            "last_started_at": _iso(last.started_at) if last else None,
            "last_ok": last.ok if last else None,
            "last_message": last.message if last else None,
            "last_success_at": _iso(ok.finished_at) if ok else None,
            "stale": refresh.is_stale(job, last, ok, now),
        })
    return out


@router.post("/refresh")
def post_refresh(force: bool = False) -> dict:
    """Start a refresh in the background (stale jobs, or all with force). Read /status for results."""
    threading.Thread(target=refresh.run_stale, kwargs={"force": force}, daemon=True).start()
    return {"started": True}
