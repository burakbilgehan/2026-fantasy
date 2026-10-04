"""Per-video extraction: transcript -> structured notes, every note quote-checked.

Output is one JSON document per video (see `extract`). It is the committed
source of truth in docs/knowledge/_data/videos/. Markdown is rendered from it.
Everything sent to `claude -p` lives in prompts/expert_digest/ (system prompt,
user prompt template, JSON schema, model and effort). See its README.md. When you
change the prompt or schema in a way that should redo old videos, raise
prompt_version in config.json; otherwise add the new version to
compatible_versions. Each note file records prompt_version and prompt_sha.
"""

import hashlib
import json
from datetime import UTC, datetime

from app.config import REPO_ROOT
from app.experts import llm
from app.experts.transcript import TimedWords, blocks, find_quote, fmt_ts, parse_ts
from app.sources.experts.youtube import Video

PROMPT_DIR = REPO_ROOT / "prompts" / "expert_digest"


def _load() -> tuple[dict, str, str, dict]:
    config = json.loads((PROMPT_DIR / "config.json").read_text(encoding="utf-8"))
    system = (PROMPT_DIR / "system.md").read_text(encoding="utf-8").strip()
    user = (PROMPT_DIR / "user_prompt.md").read_text(encoding="utf-8").strip()
    schema = json.loads((PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))
    return config, system, user, schema


CONFIG, SYSTEM, USER_PROMPT, SCHEMA = _load()
PROMPT_VERSION = CONFIG["prompt_version"]
COMPATIBLE_VERSIONS = set(CONFIG["compatible_versions"])  # notes of these versions are not re-extracted
PROMPT_SHA = hashlib.sha256((SYSTEM + USER_PROMPT + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:12]

_DASHES = (" — ", " —", "— ", "—")


def no_em_dash(value):
    """Replace em dashes in all strings of a JSON-like value (user rule)."""
    if isinstance(value, str):
        for d in _DASHES:
            value = value.replace(d, ", ")
        return value
    if isinstance(value, list):
        return [no_em_dash(v) for v in value]
    if isinstance(value, dict):
        return {k: no_em_dash(v) for k, v in value.items()}
    return value


def build_prompt(video: Video) -> str:
    return USER_PROMPT.format(
        title=video.title, channel=video.channel,
        date=video.upload_date, transcript=blocks(video.segments),
    )


def verify(notes: dict, video: Video) -> dict:
    """Check each item's quote against the transcript. Adds `seconds` and `verified`.

    `seconds` = where the quote was found (more exact than the block ts), else the
    given ts. Items with a quote that is not found keep `verified: false`.
    """
    tw = TimedWords.of(video.segments)
    for key in ("rules", "player_notes", "team_notes", "claims_to_check"):
        for item in notes.get(key, []):
            given = parse_ts(item.get("ts", ""))
            if given is not None and not 0 <= given <= video.duration + 5:
                given = None
            hit = find_quote(tw, item.get("quote", ""), given)
            item["verified"] = hit is not None
            item["match_ratio"] = round(hit[0], 2) if hit else 0.0
            item["seconds"] = hit[1] if hit else given
    return notes


def extract(video: Video, model: str = CONFIG["model"], effort: str = CONFIG["effort"]) -> dict:
    raw, usage = llm.run_json(build_prompt(video), SYSTEM, SCHEMA, model=model, effort=effort)
    notes = verify(no_em_dash(raw), video)
    return {
        "video": {
            "id": video.video_id, "title": video.title, "channel": video.channel,
            "upload_date": video.upload_date, "duration": fmt_ts(video.duration),
            "auto_captions": video.is_generated,
        },
        "prompt_version": PROMPT_VERSION,
        "prompt_sha": PROMPT_SHA,
        "extracted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "llm": usage,
        **notes,
    }
