"""YouTube video lists and transcripts for the expert digest (M8).

Listing: yt-dlp as a library, no API key. A flat playlist listing gives ids only
reliably: upload date is missing and the title can differ from the video page
(YouTube title tests, seen 2026-10-04). So metadata comes from one
`extract_info` per video.

Transcripts: youtube-transcript-api. Auto captions work (verified 2026-10-04,
a 35 min video gave 920 segments, 6017 words). Many requests in a row can get
the IP blocked (inferred); the job sleeps between videos and stops on a block.

IPv4 only: on 2026-10-04 YouTube blocked the caption endpoint (429) for the
home IPv6 address, while the same network over IPv4 still worked (verified).
Both yt-dlp and youtube-transcript-api are forced to IPv4.

Cache: data/raw/experts/youtube/{video_id}.json (metadata + segments). A cached
video is never fetched again.
"""

import json
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import RAW_DIR

CACHE_DIR = RAW_DIR / "experts" / "youtube"
_YDL_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True,
             "source_address": "0.0.0.0"}  # IPv4 (see module doc)


def _ipv4_only() -> None:
    """Make requests/urllib3 (youtube-transcript-api) resolve hosts to IPv4 only."""
    import urllib3.util.connection as conn

    conn.allowed_gai_family = lambda: socket.AF_INET


@dataclass
class Segment:
    start: float  # seconds
    text: str


@dataclass
class Video:
    video_id: str
    title: str
    channel: str
    upload_date: str  # YYYY-MM-DD
    duration: int  # seconds
    is_generated: bool  # auto captions
    segments: list[Segment]

    @staticmethod
    def from_dict(d: dict) -> "Video":
        return Video(**{**d, "segments": [Segment(**s) for s in d["segments"]]})


class TranscriptBlocked(Exception):
    """YouTube refused transcript requests (IP block or rate limit). Retry later."""


def list_playlist(url: str, retries: int = 3) -> list[str]:
    """Video ids of a playlist or channel tab, in listing order."""
    import yt_dlp

    last: Exception | None = None
    for attempt in range(retries):
        try:
            with yt_dlp.YoutubeDL({**_YDL_OPTS, "extract_flat": "in_playlist"}) as ydl:
                info = ydl.extract_info(url, download=False)
            if "entries" not in info and info.get("id"):
                return [info["id"]]  # a single video URL
            ids = [e["id"] for e in info.get("entries") or [] if e and e.get("id")]
            if ids:
                return ids
        except Exception as e:  # yt-dlp raises many types; retry all of them
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"no videos listed for {url}") from last


def cache_path(video_id: str) -> Path:
    return CACHE_DIR / f"{video_id}.json"


def load_cached(video_id: str) -> Video | None:
    path = cache_path(video_id)
    if not path.exists():
        return None
    return Video.from_dict(json.loads(path.read_text(encoding="utf-8")))


def fetch_video(video_id: str) -> Video:
    """Metadata + English transcript. Writes the cache file."""
    import yt_dlp
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import IpBlocked, RequestBlocked

    _ipv4_only()
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        meta = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    except (IpBlocked, RequestBlocked) as e:
        raise TranscriptBlocked(str(e)) from e
    d = meta.get("upload_date") or "00000000"
    video = Video(
        video_id=video_id,
        title=meta.get("title") or "",
        channel=meta.get("channel") or "",
        upload_date=f"{d[:4]}-{d[4:6]}-{d[6:]}",
        duration=int(meta.get("duration") or 0),
        is_generated=fetched.is_generated,
        segments=[Segment(start=round(s.start, 2), text=s.text) for s in fetched],
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(video_id).write_text(json.dumps(asdict(video), ensure_ascii=False), encoding="utf-8")
    return video
