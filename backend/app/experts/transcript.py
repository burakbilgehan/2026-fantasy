"""Transcript helpers: prompt blocks with timestamps, and quote verification.

Quote verification is the guard against invented notes: every LLM note carries
a short verbatim quote and a timestamp. A note is kept as verified only if the
quote is found in the transcript (fuzzy, because auto captions are noisy).
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.sources.experts.youtube import Segment

BLOCK_SECONDS = 30
QUOTE_MIN_RATIO = 0.75
NEAR_SECONDS = 120
QUOTE_MIN_WORDS = 6  # shorter quotes match by chance


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(ts: str | int | float) -> int | None:
    """"12:34" or "1:02:03" or a number of seconds. None if not parseable."""
    if isinstance(ts, (int, float)):
        return int(ts)
    parts = str(ts).strip().strip("[]").split(":")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def blocks(segments: list[Segment], seconds: int = BLOCK_SECONDS) -> str:
    """Transcript as lines "[m:ss] text", one line per `seconds` window."""
    lines: list[str] = []
    start: float | None = None
    texts: list[str] = []
    for seg in segments:
        if start is None:
            start = seg.start
        elif seg.start - start >= seconds:
            lines.append(f"[{fmt_ts(start)}] {' '.join(texts)}")
            start, texts = seg.start, []
        texts.append(seg.text.replace("\n", " ").strip())
    if texts:
        lines.append(f"[{fmt_ts(start)}] {' '.join(texts)}")
    return "\n".join(lines)


def _norm_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower().replace("’", "'")).split()


@dataclass
class TimedWords:
    words: list[str]
    times: list[float]

    @staticmethod
    def of(segments: list[Segment]) -> "TimedWords":
        words: list[str] = []
        times: list[float] = []
        for seg in segments:
            for w in _norm_words(seg.text):
                words.append(w)
                times.append(seg.start)
        return TimedWords(words, times)


def find_quote(tw: TimedWords, quote: str, near: int | None) -> tuple[float, int] | None:
    """Best match of `quote` in the transcript as (ratio, start seconds), or None.

    Searches +-NEAR_SECONDS around `near` first, then the whole transcript.
    """
    q = _norm_words(quote)
    if len(q) < QUOTE_MIN_WORDS:
        return None

    def search(lo: int, hi: int) -> tuple[float, int] | None:
        best: tuple[float, int] | None = None
        sm = SequenceMatcher(autojunk=False)
        sm.set_seq2(q)
        for i in range(lo, max(lo, hi - len(q)) + 1):
            sm.set_seq1(tw.words[i:i + len(q)])
            if sm.real_quick_ratio() < QUOTE_MIN_RATIO or sm.quick_ratio() < QUOTE_MIN_RATIO:
                continue
            r = sm.ratio()
            if best is None or r > best[0]:
                best = (r, int(tw.times[i]))
        return best if best and best[0] >= QUOTE_MIN_RATIO else None

    if near is not None:
        idx = [i for i, t in enumerate(tw.times) if abs(t - near) <= NEAR_SECONDS]
        if idx and (hit := search(idx[0], idx[-1] + 1)):
            return hit
    return search(0, len(tw.words))
