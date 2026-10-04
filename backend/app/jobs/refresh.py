"""Automatic refresh of fast-changing data (T-026): rosters, minutes, depth charts.

The backend runs `run_stale()` on start and then every CHECK_EVERY seconds while
it runs (`start_loop()`, called from the FastAPI lifespan). A job runs when its
last successful run is older than its TTL. A failed job waits RETRY_AFTER before
the next try, so a blocked source is not hit every tick. Jobs are isolated: one
failure does not stop the others. Every run is a row in `sync_runs`.

Not here on purpose: `players-sync` (Yahoo, ESPN). The Yahoo feed is on demand
only (decision in app/api/players.py); run it by hand, also on draft morning.

Manual: `make refresh` (stale jobs only) or `make refresh ARGS=--force`.
Kill switch: AUTO_REFRESH=0 in .env stops the loop (manual refresh still works).
"""

import logging
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import SyncRun

log = logging.getLogger(__name__)

CHECK_EVERY = 3600  # seconds
RETRY_AFTER = timedelta(hours=1)


@dataclass(frozen=True)
class Job:
    name: str
    ttl: timedelta
    run: Callable[[], str]  # returns a one-line summary


def _roles(key: str) -> Callable[[], str]:
    def run() -> str:
        from app.jobs.sync_roles import sync_one

        return sync_one(key).summary()
    return run


def _game_logs_current() -> str:
    from app.jobs.sync_game_logs import sync_current

    return "; ".join(f"{t}: {sum(r.rows.values())} games" for t, r in sync_current().items())


JOBS = {j.name: j for j in (
    Job("hashtag", timedelta(hours=6), _roles("hashtag")),
    Job("darko", timedelta(hours=12), _roles("darko")),
    Job("fantasypros", timedelta(hours=12), _roles("fantasypros")),
    Job("vegas", timedelta(hours=24), _roles("vegas")),
    Job("game_logs_current", timedelta(hours=6), _game_logs_current),
)}

_lock = threading.Lock()  # one refresh at a time (loop tick or API call)


def _utc(t: datetime | None) -> datetime | None:
    return t.replace(tzinfo=UTC) if t and t.tzinfo is None else t


def last_runs(db) -> dict[str, dict[str, SyncRun | None]]:
    """{job: {"last": latest run, "last_ok": latest successful run}}."""
    out = {}
    for name in JOBS:
        runs = db.scalars(select(SyncRun).where(SyncRun.job == name)
                          .order_by(SyncRun.started_at.desc()).limit(50)).all()
        out[name] = {"last": runs[0] if runs else None,
                     "last_ok": next((r for r in runs if r.ok), None)}
    return out


def is_stale(job: Job, last: SyncRun | None, last_ok: SyncRun | None, now: datetime) -> bool:
    if last is not None and last.ok is False and now - _utc(last.started_at) < RETRY_AFTER:
        return False
    return last_ok is None or now - _utc(last_ok.finished_at) >= job.ttl


def run_job(job: Job) -> SyncRun:
    from app.db import SessionLocal

    with SessionLocal.begin() as db:
        run = SyncRun(job=job.name, started_at=datetime.now(UTC))
        db.add(run)
    try:
        run.message, run.ok = job.run(), True
    except Exception as e:  # noqa: BLE001  (isolate jobs; the message keeps the reason)
        log.exception("refresh job %s failed", job.name)
        run.message, run.ok = f"{type(e).__name__}: {e}"[:500], False
    run.finished_at = datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.merge(run)
    return run


def run_stale(force: bool = False, names: list[str] | None = None) -> list[SyncRun]:
    from app.db import SessionLocal

    if not _lock.acquire(blocking=False):
        return []  # another refresh is running
    try:
        now = datetime.now(UTC)
        with SessionLocal() as db:
            state = last_runs(db)
        todo = [j for name, j in JOBS.items() if (names is None or name in names)
                and (force or is_stale(j, **state[name], now=now))]
        return [run_job(j) for j in todo]
    finally:
        _lock.release()


def enabled() -> bool:
    return os.environ.get("AUTO_REFRESH", "1") != "0"


def start_loop(stop: threading.Event) -> threading.Thread:
    def loop() -> None:
        while not stop.is_set():
            try:
                run_stale()
            except Exception:  # noqa: BLE001  (the loop must survive a DB error)
                log.exception("refresh loop tick failed")
            stop.wait(CHECK_EVERY)

    t = threading.Thread(target=loop, name="refresh", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    from app.db import init_db

    init_db()
    args = sys.argv[1:]
    force = "--force" in args
    names = [a for a in args if not a.startswith("--")] or None
    runs = run_stale(force=force, names=names)
    for r in runs:
        print(f"{r.job}: {'ok' if r.ok else 'FAILED'}: {r.message}")
    if not runs:
        print("All jobs are fresh (or a refresh is already running). ARGS=--force runs all.")
