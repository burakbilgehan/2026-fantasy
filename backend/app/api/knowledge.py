"""Profile tags (T-022) for the tag filter and the draft panel (T-018)."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import KnowledgeTag, Player

router = APIRouter(prefix="/api/knowledge")


def _row(t: KnowledgeTag) -> dict:
    return {"tag": t.tag, "kind": t.kind, "channel": t.channel, "detail": t.detail, "until": t.until,
            "classified": t.classified}


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
        return [_row(t) for t in rows]
