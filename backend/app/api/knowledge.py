"""Profile tags (T-022) for the tag filter and the draft panel (T-018)."""

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import KnowledgeTag, Player

router = APIRouter(prefix="/api/knowledge")


VIDEO_DIR = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "_data" / "videos"


@lru_cache(maxsize=256)
def _video(video_id: str) -> dict | None:
    path = VIDEO_DIR / f"{video_id}.json"
    if not re.fullmatch(r"[\w-]+", video_id) or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def source(ref: str) -> dict:
    """A tag source id ("{video}:p{i}" player note, "{video}:t{i}" team note, or "stats") as the note
    text, the quote, the video and a link at the timestamp."""
    if ref == "stats":
        return {"id": ref, "text": "Our own stats (category profile).", "quote": None, "url": None,
                "date": None, "video": None}
    m = re.fullmatch(r"([\w-]+):([pt])(\d+)", ref)
    doc = _video(m.group(1)) if m else None
    notes = (doc or {}).get("player_notes" if m and m.group(2) == "p" else "team_notes", [])
    n = notes[int(m.group(3))] if m and int(m.group(3)) < len(notes) else None
    if not n:
        return {"id": ref, "text": None, "quote": None, "url": None, "date": None, "video": None}
    v = doc["video"]
    return {"id": ref, "text": n.get("text"), "quote": n.get("quote"),
            "url": f"https://youtu.be/{v['id']}?t={int(n.get('seconds') or 0)}",
            "date": v.get("upload_date"), "video": v.get("title")}


def _row(t: KnowledgeTag, sources: bool = False) -> dict:
    out = {"tag": t.tag, "kind": t.kind, "channel": t.channel, "detail": t.detail, "until": t.until,
           "classified": t.classified}
    if sources:
        out["sources"] = [source(r) for r in (t.sources or [])]
    return out


@router.get("/tags")
def get_tags(subject: str = "player") -> list[dict]:
    """Canonical tags with the number of players (or teams) that carry each one."""
    with SessionLocal() as db:
        rows = db.execute(
            select(KnowledgeTag.tag, KnowledgeTag.kind, KnowledgeTag.channel, func.count())
            .where(KnowledgeTag.subject == subject)
            .group_by(KnowledgeTag.tag, KnowledgeTag.kind, KnowledgeTag.channel)
            .order_by(func.count().desc())).all()
    return [{"tag": t, "kind": k, "channel": c, "count": n} for t, k, c, n in rows]


@router.get("/tags/{tag}")
def get_tag(tag: str) -> list[dict]:
    """Players with this tag (example: all "buy low" players)."""
    with SessionLocal() as db:
        rows = db.execute(select(KnowledgeTag, Player).join(Player, Player.id == KnowledgeTag.player_pk)
                          .where(KnowledgeTag.tag == tag)).all()
    return [{"player_pk": p.id, "name": f"{p.first_name} {p.last_name}".strip(), "team": p.team, **_row(t)}
            for t, p in rows]


@router.get("/players/{player_pk}/tags")
def get_player_tags(player_pk: int) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(KnowledgeTag).where(KnowledgeTag.player_pk == player_pk))
        return [_row(t, sources=True) for t in rows]
