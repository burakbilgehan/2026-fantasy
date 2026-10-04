"""Interactive expert digest runner: batches, progress bars, safe stop.

Usage: python -m app.jobs.expert_run URL --since ID [--batch 10] [--model M] [--effort E]
Make:  make expert-run   (defaults: Locked On channel, since HxQjagSTTAM, batch 10)

Runs all videos still to do, in batches. Transcripts are fetched one by one
(YouTube); the LLM calls of a batch run in parallel (--parallel, default = batch). After each batch the knowledge base is
re-rendered, so it is usable at any point.
Ctrl-C once: start no new video, let running calls finish. Ctrl-C twice: kill
all running calls now (those videos run again next time). Done videos are never redone, so a new
run continues where the last one stopped.
"""

import argparse
import signal
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn,
)
from rich.text import Text

from app.experts import extract, llm
from app.jobs import digest_experts as dx
from app.sources.experts import youtube

console = Console()


class Stop:
    requests = 0
    last = 0.0

    @classmethod
    def handler(cls, signum, frame):
        now = time.monotonic()
        if now - cls.last < 1.0:  # one key press can arrive twice (wrapper forwards it)
            return
        cls.last = now
        cls.requests += 1
        if cls.requests >= 2:
            raise KeyboardInterrupt


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--since")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--parallel", type=int, help="LLM calls at once (default: batch size)")
    ap.add_argument("--cached-only", action="store_true",
                    help="only videos whose transcript is already cached; no YouTube transcript request")
    ap.add_argument("--model", default=extract.CONFIG["model"])
    ap.add_argument("--effort", default=extract.CONFIG["effort"])
    a = ap.parse_args(argv)
    a.parallel = a.parallel or a.batch

    with console.status("Listing videos and loading players..."):
        known = dx.players()
        ids, todo = dx.select_ids(a.url, a.since, force=False)
    skipped: list[str] = []
    if a.cached_only:
        skipped = [v for v in todo if not youtube.cache_path(v).exists()]
        todo = [v for v in todo if youtube.cache_path(v).exists()]
        if skipped:
            console.print(f"[yellow]{len(skipped)} videos have no cached transcript; skipped (--cached-only).[/]")
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    console.print(f"[bold]{len(ids)}[/] videos in range, [green]{len(ids) - len(todo) - len(skipped)}[/] done, "
                  f"[yellow]{len(todo)}[/] to do in {len(batches)} batches of {a.batch}. "
                  f"Model {a.model}, effort {a.effort}, up to {a.parallel} LLM calls at once.")
    console.print("[dim]Ctrl-C once: start no new video, let running ones finish. Twice: stop now.[/]\n")
    if not todo:
        return

    bars = Progress(
        TextColumn("{task.description:<10}"), BarColumn(bar_width=40), MofNCompleteColumn(),
        console=console,
    )
    current = Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(),
                       console=console)  # one row per running step
    started = time.monotonic()
    stats = {"ok": 0, "notes": 0, "unverified": 0, "failed": 0, "cost": 0.0, "llm_s": 0.0}

    def hms(seconds: float) -> str:
        m, sec = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    def stats_line() -> Text:
        handled = stats["ok"] + stats["failed"]
        left = len(todo) - handled
        elapsed = time.monotonic() - started
        per_video = elapsed / handled if handled else None
        eta = hms(per_video * left) if per_video else "?"
        avg_cost = stats["cost"] / stats["ok"] if stats["ok"] else None
        total_cost = f"${stats['cost'] + avg_cost * left:.2f}" if avg_cost else "?"
        stop = "\n[yellow]Stopping: no new videos, waiting for running ones.[/]" if Stop.requests == 1 else ""
        return Text.from_markup(
            f"Elapsed [bold]{hms(elapsed)}[/]   left about [bold]{eta}[/]   "
            f"videos: processed [green]{stats['ok']}[/], failed [red]{stats['failed']}[/], "
            f"left [yellow]{left}[/]\n"
            f"List price (not billed): spent [bold]${stats['cost']:.2f}[/], "
            f"projected total {total_cost}   "
            f"notes {stats['notes']} ([red]{stats['unverified']}[/] unverified)   "
            f"avg LLM {stats['llm_s'] / stats['ok'] if stats['ok'] else 0:.0f} s/video{stop}")

    all_task = bars.add_task("All", total=len(ids), completed=len(ids) - len(todo) - len(skipped))
    batch_task = bars.add_task("Batch", total=len(batches[0]))
    signal.signal(signal.SIGINT, Stop.handler)
    stopped_by = None
    pool = ThreadPoolExecutor(max_workers=a.parallel)

    def finished(live, vid: str, status: str, out) -> None:
        nonlocal stopped_by
        if status == "ok":
            items = dx.note_items(out)
            bad = sum(not i["verified"] for i in items)
            llm_info = out["llm"]
            stats["ok"] += 1
            stats["notes"] += len(items)
            stats["unverified"] += bad
            stats["cost"] += llm_info.get("cost_usd_list") or 0
            stats["llm_s"] += (llm_info.get("duration_ms") or 0) / 1000
            v = out["video"]
            live.console.print(
                f"[green]ok[/] {v['upload_date']} {v['title'][:60]}  {len(items)} notes, {bad} unverified, "
                f"{(llm_info.get('duration_ms') or 0) / 1000:.0f} s, ${llm_info.get('cost_usd_list') or 0:.2f}")
        else:
            stats["failed"] += 1
            live.console.print(f"[red]{status}[/] {vid}: {out}")
            if status in ("blocked", "usage_limit"):
                stopped_by = stopped_by or status
        bars.advance(batch_task)
        bars.advance(all_task)

    try:
        with Live(console=console, refresh_per_second=4,
                  get_renderable=lambda: Group(bars, current, stats_line())) as live:
            for b, batch in enumerate(batches, 1):
                bars.reset(batch_task, total=len(batch), description=f"Batch {b}/{len(batches)}")
                running: dict = {}  # future -> (vid, progress task)

                def collect(timeout: float) -> None:
                    done, _ = wait(list(running), timeout=timeout, return_when=FIRST_COMPLETED)
                    for fut in done:
                        vid, task = running.pop(fut)
                        current.remove_task(task)
                        finished(live, vid, *fut.result())

                # Transcripts one by one (YouTube); each LLM call starts as soon as its transcript is in.
                for vid in batch:
                    if Stop.requests or stopped_by:
                        stopped_by = stopped_by or "user"
                        break
                    fetch_task = current.add_task(f"{vid} fetching transcript")
                    status, video = dx.fetch(vid)
                    current.remove_task(fetch_task)
                    if status != "ok":
                        finished(live, vid, status, video)
                        continue
                    task = current.add_task(f"LLM  {video.title[:70]}")
                    running[pool.submit(dx.summarize, video, a.model, a.effort)] = (vid, task)
                    collect(0)
                while running:
                    collect(0.5)
                if stopped_by:
                    break
                fetch_task = current.add_task("rendering knowledge base")
                dx.render_all(known)
                current.remove_task(fetch_task)
                live.console.print(f"[bold]Batch {b} done.[/] Knowledge base updated.")
    except KeyboardInterrupt:
        stopped_by = "user (now)"
        llm.kill_all()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    result = dx.render_all(known)
    minutes = (time.monotonic() - started) / 60
    console.print(
        f"\n[bold]Run finished[/]{f' (stopped by {stopped_by})' if stopped_by else ''}: "
        f"{stats['ok']} videos, {stats['failed']} failed, {minutes:.1f} min, "
        f"${stats['cost']:.2f} list price (subscription, not billed). Knowledge base: {result}")
    console.print("[dim]Run the same command again to continue.[/]")


if __name__ == "__main__":
    main(sys.argv[1:])
