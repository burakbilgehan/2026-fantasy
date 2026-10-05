"""Automatic refresh of fast-changing data (T-026): rosters, minutes, depth charts.

The backend runs `run_stale()` on start and then every CHECK_EVERY seconds while
it runs (`start_loop()`, called from the FastAPI lifespan). A job runs when its
last successful run is older than its TTL. A failed job waits RETRY_AFTER before
the next try, so a blocked source is not hit every tick. Jobs are isolated: one
failure does not stop the others. Every run is a row in `sync_runs`.

Also here: the ESPN player feed (`espn`, projections with projected minutes in
player_projections.min), Fantrax ADP (`fantrax`), FanScout projections (`fanscout`, with
projected minutes) and player birth dates (`birthdates`).
Yahoo player feed (`yahoo`): weekly (user, 2026-10-05: no source may be older than a week;
before that the feed was on demand only). Run it by hand on draft morning too.
Fantrax projections need the user's logged-in Chrome tab, so they are a status row only
(`fantrax_projections`): when they are older than a week, ask Claude to refresh them.

Freshness rule (user, 2026-10-05): every source is fetched again when its data is older than
its TTL, and no TTL is above 7 days. A job counts as fresh by its last successful run or by the
newest `fetched_at` of its data, whichever is newer, so a manual sync also counts.

One command: `make sources` prints every source with its last fetch and age, then fetches only
the stale ones. `make refresh ARGS=--force` fetches all.
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


def _players(key: str) -> Callable[[], str]:
    def run() -> str:
        from app.jobs.sync_players import sync

        # Ambiguous names make new player rows; on demand the job prints them, here the summary keeps the count.
        return "; ".join(f"{r.source}: {sum(r.how.values())} players, matched by {dict(r.how)}"
                         + (f", {len(r.ambiguous)} ambiguous new rows" if r.ambiguous else "")
                         for r in sync([key]))
    return run


def _birthdates() -> str:
    from app.jobs.sync_birthdates import sync

    return sync().summary()


def _projection_base() -> str:
    import contextlib
    import io

    from app.jobs.projection import cmd_run

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_run()
    return buf.getvalue().strip().splitlines()[-1]


def _game_logs_current() -> str:
    from app.jobs.sync_game_logs import sync_current

    return "; ".join(f"{t}: {sum(r.rows.values())} games" for t, r in sync_current().items())


JOBS = {j.name: j for j in (
    Job("hashtag", timedelta(hours=6), _roles("hashtag")),
    Job("darko", timedelta(hours=12), _roles("darko")),
    Job("fantasypros", timedelta(hours=12), _roles("fantasypros")),
    Job("vegas", timedelta(hours=24), _roles("vegas")),
    Job("game_logs_current", timedelta(hours=6), _game_logs_current),
    Job("espn", timedelta(hours=12), _players("espn")),
    Job("fantrax", timedelta(hours=12), _players("fantrax")),
    Job("fanscout", timedelta(hours=24), _players("fanscout")),
    Job("birthdates", timedelta(days=7), _birthdates),
    Job("yahoo", timedelta(days=7), _players("yahoo")),
    Job("nba_rosters", timedelta(days=1), _players("nba")),  # NBA.com: the only team source
    # Own projection (T-025): rebuild the base from the newest sources and apply the stored LLM and
    # manual adjustments. Free, seconds. The paid LLM layer runs with `make projection-update`.
    Job("projection_base", timedelta(days=1), _projection_base),
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


# Where each job's data lives: (table, source column value). Used for the age of the data itself.
def _data_tables():
    from app.models import (DepthChartEntry, PlayerGameLog, PlayerMarketValue, PlayerMinutesProjection,
                            PlayerProjection, TeamWinTotal)

    return {
        "hashtag": (DepthChartEntry, "hashtag"), "darko": (PlayerMinutesProjection, "darko"),
        "fantasypros": (PlayerMinutesProjection, "fantasypros"), "vegas": (TeamWinTotal, None),
        "game_logs_current": (PlayerGameLog, None), "espn": (PlayerProjection, "espn"),
        "fantrax": (PlayerMarketValue, "fantrax"), "fanscout": (PlayerProjection, "fanscout"),
        "yahoo": (PlayerProjection, "yahoo"), "fantrax_projections": (PlayerProjection, "fantrax"),
        "nba_rosters": None, "projection_base": (PlayerProjection, "own-base"),
    }


def data_times(db) -> dict[str, datetime | None]:
    """Newest fetched_at of each job's data."""
    from sqlalchemy import func

    out = {}
    for name, spec in _data_tables().items():
        if spec is None:
            continue
        model, src = spec
        q = select(func.max(model.fetched_at))
        if src is not None:
            q = q.where(model.source == src)
        out[name] = _utc(db.scalar(q))
    return out


def fresh_at(last_ok: SyncRun | None, data_time: datetime | None) -> datetime | None:
    times = [t for t in (_utc(last_ok.finished_at) if last_ok else None, data_time) if t]
    return max(times) if times else None


def is_stale(job: Job, last: SyncRun | None, last_ok: SyncRun | None, now: datetime,
             data_time: datetime | None = None) -> bool:
    if last is not None and last.ok is False and now - _utc(last.started_at) < RETRY_AFTER:
        return False
    t = fresh_at(last_ok, data_time)
    return t is None or now - t >= job.ttl


MANUAL = {"fantrax_projections": timedelta(days=7)}  # status only: refreshed through Chrome by Claude


def status_table(db) -> str:
    now = datetime.now(UTC)
    state, dt = last_runs(db), data_times(db)
    lines = [f"{'source':22} {'last fetch (UTC)':17} {'age':>8} {'max age':>8}  status"]
    for name, job in list(JOBS.items()) + [(n, None) for n in MANUAL]:
        ttl = job.ttl if job else MANUAL[name]
        t = fresh_at(state[name]["last_ok"], dt.get(name)) if job else dt.get(name)
        age = now - t if t else None
        stale = age is None or age >= ttl
        if job is None:
            status = "STALE: ask Claude to refresh via Chrome" if stale else "ok (manual source)"
        else:
            last = state[name]["last"]
            failed = last is not None and last.ok is False
            status = ("stale, will fetch" if stale else "ok") + (" (last try failed)" if failed else "")
        age_s = f"{age.total_seconds() / 86400:.1f}d" if age else "-"
        ttl_s = f"{ttl.total_seconds() / 86400:g}d"
        lines.append(f"{name:22} {(f'{t:%Y-%m-%d %H:%M}' if t else 'never'):17} {age_s:>8} {ttl_s:>8}  {status}")
    return "\n".join(lines)


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
            state, dt = last_runs(db), data_times(db)
        todo = [j for name, j in JOBS.items() if (names is None or name in names)
                and (force or is_stale(j, **state[name], now=now, data_time=dt.get(name)))]
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

    from app.db import SessionLocal

    init_db()
    args = sys.argv[1:]
    if "--status" in args:
        with SessionLocal() as db:
            print(status_table(db))
        print()
    force = "--force" in args
    names = [a for a in args if not a.startswith("--")] or None
    runs = run_stale(force=force, names=names)
    for r in runs:
        print(f"{r.job}: {'ok' if r.ok else 'FAILED'}: {r.message}")
    if not runs:
        print("All jobs are fresh (or a refresh is already running). ARGS=--force runs all.")
    if "--status" in args and runs:
        with SessionLocal() as db:
            print()
            print(status_table(db))
