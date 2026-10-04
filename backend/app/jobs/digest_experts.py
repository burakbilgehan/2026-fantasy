"""Expert digest (M8, first part): YouTube playlist -> notes -> docs/knowledge/.

Usage:
  python -m app.jobs.digest_experts URL [--since ID] [--limit N] [--force] [--model M] [--effort E]
  python -m app.jobs.digest_experts --show-prompt VIDEO_ID   (print the exact command and stdin)
  python -m app.jobs.digest_experts --render     (markdown only, no network, no LLM)

URL: a playlist, a channel tab, or one video. --since ID: with a channel /videos
tab (newest first), use only the videos newer than ID, and ID itself. Videos run
oldest first. --limit N: stop after N new extractions (done videos do not count),
so repeated runs work as batches. Per video: transcript (cached in
data/raw/experts/youtube/), one `claude -p` call, quote check, then JSON in
docs/knowledge/_data/videos/{id}.json. A video with JSON of the current
PROMPT_VERSION is skipped unless --force. Sequential, with a pause after each
YouTube fetch. On a YouTube block the run stops; the next run resumes.
"""

import argparse
import functools
import json
import random
import shlex
import sys
import time

print = functools.partial(print, flush=True)  # progress shows in redirected logs

from app.config import REPO_ROOT
from app.experts import extract, llm, match, render
from app.sources.experts import youtube

KB_DIR = REPO_ROOT / "docs" / "knowledge"
NOTES_DIR = KB_DIR / "_data" / "videos"
ALIASES = KB_DIR / "aliases.json"
FETCH_PAUSE_SECONDS = (20, 30)  # random pause after each YouTube fetch (5 s got a 429 block, 2026-10-04)


def load_docs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(NOTES_DIR.glob("*.json"))]


def players() -> list[match.KnownPlayer]:
    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        return match.load_players(db)


def render_all(known: list[match.KnownPlayer]) -> dict:
    """Learn nicknames from all notes, save them to aliases.json, then render."""
    aliases = {"players": {}, "teams": {}, **match.load_aliases(ALIASES)}
    docs = load_docs()
    matcher = match.Matcher(known, {**aliases, "learned_players": {}})
    pairs = []
    for doc in docs:
        for i in doc["player_notes"]:
            p, how = matcher.player_how(i["player"], i.get("said_as", ""), i.get("team", ""))
            if p and how in ("exact", "fuzzy") and i.get("verified"):
                pairs.append((i.get("said_as", ""), p))
    aliases["learned_players"] = match.learn_nicknames(pairs)
    ALIASES.write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return render.render(docs, match.Matcher(known, aliases), KB_DIR)


def is_done(video_id: str) -> bool:
    path = NOTES_DIR / f"{video_id}.json"
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get(
        "prompt_version") in extract.COMPATIBLE_VERSIONS


def select_ids(url: str, since: str | None, force: bool) -> tuple[list[str], list[str]]:
    """(all ids in range, ids still to do). Oldest first when `since` is given."""
    ids = youtube.list_playlist(url)
    if since:
        if since not in ids:
            raise SystemExit(f"{since} is not in the listing")
        ids = list(reversed(ids[:ids.index(since) + 1]))
    return ids, [v for v in ids if force or not is_done(v)]


def fetch(vid: str) -> tuple[str, "youtube.Video | str"]:
    """Transcript from cache or YouTube. ("ok", video) or ("blocked" | "no_transcript", message).

    Call from one thread only: it pauses after each YouTube fetch.
    """
    video = youtube.load_cached(vid)
    if video is not None:
        return "ok", video
    try:
        return "ok", youtube.fetch_video(vid)
    except youtube.TranscriptBlocked as e:
        return "blocked", str(e)[:300]
    except Exception as e:  # no captions, private video, removed video
        return "no_transcript", f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        time.sleep(random.uniform(*FETCH_PAUSE_SECONDS))


def summarize(video: "youtube.Video", model: str, effort: str,
              retries: int = 1) -> tuple[str, dict | str]:
    """LLM + save. ("ok", doc) or ("usage_limit" | "llm_failed", message). Thread safe."""
    for attempt in range(retries + 1):
        try:
            doc = extract.extract(video, model=model, effort=effort)
            break
        except llm.UsageLimit as e:
            return "usage_limit", str(e)[:300]
        except Exception as e:
            if attempt == retries:
                return "llm_failed", str(e)[:300]
            if llm.ABORTED.wait(30):  # rate limit or overload: wait once, then retry
                return "llm_failed", "aborted"
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = NOTES_DIR / f"{video.video_id}.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(NOTES_DIR / f"{video.video_id}.json")  # never a half-written note file
    return "ok", doc


def process(vid: str, model: str, effort: str) -> tuple[str, dict | str]:
    """One video, sequential. Status: "ok", "blocked", "no_transcript", "usage_limit", "llm_failed"."""
    status, video = fetch(vid)
    if status != "ok":
        return status, video
    return summarize(video, model, effort)


def note_items(doc: dict) -> list[dict]:
    return [i for k in ("rules", "player_notes", "team_notes", "claims_to_check") for i in doc[k]]


def digest(url: str, since: str | None, limit: int | None, force: bool, model: str,
           effort: str) -> None:
    known = players()
    ids, todo = select_ids(url, since, force)
    print(f"{len(ids)} in range, {len(ids) - len(todo)} done, {len(todo)} to do"
          + (f", this run: {min(limit, len(todo))}" if limit else ""))
    if limit:
        todo = todo[:limit]
    started, cost, made = time.monotonic(), 0.0, 0
    for n, vid in enumerate(todo, 1):
        status, out = process(vid, model, effort)
        if status in ("blocked", "usage_limit"):
            print(f"{status}, stopping. Run again later. ({out})")
            break
        if status != "ok":
            print(f"[{n}/{len(todo)}] {vid} {status}: {out}")
            continue
        made += 1
        cost += out["llm"].get("cost_usd_list") or 0
        items = note_items(out)
        bad = sum(not i["verified"] for i in items)
        v = out["video"]
        print(f"[{n}/{len(todo)}] {vid} {v['upload_date']} {v['title'][:60]!r}: "
              f"{len(items)} notes, {bad} unverified, {out['llm']['duration_ms'] / 1000:.0f} s, "
              f"${out['llm'].get('cost_usd_list') or 0:.2f} list price")
    print(f"Run: {made} videos, {time.monotonic() - started:.0f} s, ${cost:.2f} list price "
          f"(subscription: not billed, counts toward usage limits)")
    print(render_all(known))


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--since")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=extract.CONFIG["model"])
    ap.add_argument("--effort", default=extract.CONFIG["effort"])
    ap.add_argument("--show-prompt", metavar="VIDEO_ID")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    if a.show_prompt:
        video = youtube.load_cached(a.show_prompt) or youtube.fetch_video(a.show_prompt)
        cmd = llm.command(extract.SYSTEM, extract.SCHEMA, a.model, a.effort)
        print("# Command (stdin = the prompt below):")
        print(shlex.join(cmd))
        print("\n# Prompt (stdin):")
        print(extract.build_prompt(video))
    elif a.render:
        print(render_all(players()))
    elif a.url:
        digest(a.url, a.since, a.limit, a.force, a.model, a.effort)
    else:
        ap.error("give a URL or --render")


if __name__ == "__main__":
    main(sys.argv[1:])
