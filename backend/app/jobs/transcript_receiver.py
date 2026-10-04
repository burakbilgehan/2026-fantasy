"""Local receiver for transcripts read in the user's Chrome (YouTube transcript panel).

Why: YouTube rate-limits the caption endpoint that youtube-transcript-api uses
(429 / IpBlocked on 2026-10-04, after about 30 fast requests; VPN IPs get
RequestBlocked). The transcript panel on the watch page, in the user's own
logged-in browser, still works. A script in a YouTube tab reads the panel and
POSTs each video here. This server writes the same cache file as
`youtube.fetch_video`, so `make expert-run` then needs no YouTube request.

Usage: python -m app.jobs.transcript_receiver   (listens on 127.0.0.1:8765)
POST /transcript  {"video_id", "title", "channel", "publish_date": "YYYY-MM-DD...",
                   "duration": seconds, "segments": [{"ts": "m:ss", "text": str}]}
GET  /status      ids already in the cache
GET  /grab.js?id= the page script (app/sources/experts/chrome_transcript_grab.js) for one video
"""

import json
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.experts.transcript import parse_ts
from app.sources.experts import youtube

PORT = 8765
GRAB_JS = Path(__file__).resolve().parents[1] / "sources" / "experts" / "chrome_transcript_grab.js"
ORIGIN = "https://www.youtube.com"


def to_video(payload: dict) -> youtube.Video:
    """Pure: panel payload -> cache Video. Drops empty and pure-noise segments."""
    segments = []
    for s in payload["segments"]:
        start = parse_ts(s.get("ts", ""))
        text = " ".join(s.get("text", "").split())
        if start is None or not text:
            continue
        segments.append(youtube.Segment(start=float(start), text=text))
    if not segments:
        raise ValueError("no segments")
    return youtube.Video(
        video_id=payload["video_id"], title=payload.get("title", ""),
        channel=payload.get("channel", ""), upload_date=str(payload.get("publish_date", ""))[:10],
        duration=int(payload.get("duration") or 0),
        is_generated=True,  # the panel shows the auto transcript for this channel (assumed)
        segments=segments,
    )


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/grab.js":
            vid = parse_qs(url.query).get("id", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return self._reply(400, {"error": "bad id"})
            data = GRAB_JS.read_text(encoding="utf-8").replace("__ID__", vid).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path != "/status":
            return self._reply(404, {"error": "not found"})
        ids = sorted(p.stem for p in youtube.CACHE_DIR.glob("*.json"))
        self._reply(200, {"cached": ids})

    def do_POST(self) -> None:
        if self.path != "/transcript":
            return self._reply(404, {"error": "not found"})
        try:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            video = to_video(payload)
        except (ValueError, KeyError, TypeError) as e:
            return self._reply(400, {"error": str(e)})
        youtube.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = youtube.cache_path(video.video_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(video), ensure_ascii=False), encoding="utf-8")
        tmp.replace(youtube.cache_path(video.video_id))
        print(f"saved {video.video_id} {video.upload_date} {len(video.segments)} segments {video.title[:60]!r}",
              flush=True)
        self._reply(200, {"saved": video.video_id, "segments": len(video.segments)})

    def log_message(self, *args) -> None:  # quiet
        pass


if __name__ == "__main__":
    print(f"listening on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
