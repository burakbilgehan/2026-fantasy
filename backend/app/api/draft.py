"""Live draft state for the frontend (polled every few seconds).

Raw facts: picks, money, the open nomination, who is on the clock (`/live/{league_id}`).
The draft board (T-018): teams with money, open slots and max bid, picks and the open nomination
with our player ids (`/live/{league_id}/board`).
"""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db import SessionLocal
from app.draft import live, money
from app.models import Player, PlayerExternalId

router = APIRouter(prefix="/api/draft")

_NAMES_TTL = 300  # seconds; players-sync does not run during a draft
_names: dict[str, str] = {}
_names_at = 0.0


def _player_names() -> dict[str, str]:
    """Yahoo player id -> full name, from the players table. Cached."""
    global _names, _names_at
    if not _names or time.monotonic() - _names_at > _NAMES_TTL:
        try:
            with SessionLocal() as db:
                rows = db.execute(
                    select(PlayerExternalId.external_id, Player.first_name, Player.last_name)
                    .join(Player, Player.id == PlayerExternalId.player_pk)
                    .where(PlayerExternalId.source == "yahoo")
                ).all()
        except OperationalError:
            return {}  # No players table yet (fresh DB). Ids are shown instead of names.
        _names = {pid: f"{first} {last}".strip() for pid, first, last in rows}
        _names_at = time.monotonic()
    return _names


_pks: dict[str, int] = {}
_pks_at = 0.0


def _yahoo_pks() -> dict[str, int]:
    """Yahoo player id -> player_pk. Cached like the names."""
    global _pks, _pks_at
    if not _pks or time.monotonic() - _pks_at > _NAMES_TTL:
        with SessionLocal() as db:
            rows = db.execute(select(PlayerExternalId.external_id, PlayerExternalId.player_pk)
                              .where(PlayerExternalId.source == "yahoo")).all()
        _pks = dict(rows)
        _pks_at = time.monotonic()
    return _pks


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


def _kind(league_id: str) -> str:
    return "league" if league_id == get_settings().yahoo_league_id else "mock"


def _view(d: live.LiveDraft, names: dict[str, str]) -> dict:
    s = d.state
    team_ids = sorted(set(d.team_names) | set(s.server_budgets) | set(s.nomination_order))
    picks = sorted(s.picks.values(), key=lambda p: p.pick_no)
    n = s.nomination
    return {
        "league_id": d.league_id,
        "kind": _kind(d.league_id),
        "my_team_id": d.my_team_id,
        "budget": s.budget,
        "last_event_at": _iso(d.last_event_at),
        "server_time": datetime.now(UTC).isoformat(),
        "teams": [
            {
                "team_id": t,
                "name": d.team_names.get(t),
                # Computed from picks. Server `$|` comes only on connect, so it is stale after
                # the next sale. Each `$|` is checked against this value (mismatch -> `warnings`).
                "money_left": s.money_left(t),
                "spent": s.spent(t),
                "players": sum(1 for p in picks if p.team_id == t),
                "online": t in s.online,
                "autopick": t in s.autopick,
            }
            for t in team_ids
        ],
        "nomination_order": list(s.nomination_order),
        "on_the_clock": (
            {"pick_no": s.on_the_clock.pick_no, "team_id": s.on_the_clock.team_id} if s.on_the_clock else None
        ),
        "nomination": (
            {
                "pick_no": n.pick_no,
                "player_id": n.player_id,
                "player_name": names.get(n.player_id),
                "nominating_team_id": n.nominating_team_id,
                "high_bid": n.high_bid,
                "high_team_id": n.high_team_id,
                "bids": [{"at": _iso(at), "team_id": t, "amount": a} for at, t, a in n.bids],
            }
            if n else None
        ),
        "picks": [
            {
                "pick_no": p.pick_no,
                "player_id": p.player_id,
                "player_name": names.get(p.player_id),
                "team_id": p.team_id,
                "price": p.price,
                "roster_slot": p.roster_slot,
                "nominating_team_id": p.nominating_team_id,
                "sold_at": _iso(p.sold_at),
            }
            for p in picks
        ],
        "warnings": list(s.warnings),
        "unknown": dict(s.unknown),
    }


@router.get("/live")
async def list_live() -> list[dict]:
    """Drafts with capture files, newest event first."""
    out = []
    for league_id in live.league_ids():
        d = live.get(league_id)
        if d is None:
            continue
        with live.lock:
            out.append({
                "league_id": league_id,
                "kind": _kind(league_id),
                "my_team_id": d.my_team_id,
                "last_event_at": _iso(d.last_event_at),
                "picks": len(d.state.picks),
            })
    return sorted(out, key=lambda r: r["last_event_at"] or "", reverse=True)


@router.get("/live/{league_id}")
async def get_live(league_id: str) -> dict:
    names = _player_names()
    d = live.get(league_id)
    if d is None:
        raise HTTPException(404, f"No capture for league {league_id}")
    with live.lock:
        return _view(d, names)



@router.get("/live/{league_id}/board")
def live_board(league_id: str) -> dict:
    """Teams, picks and the open nomination with player_pk, for the draft panel (T-018).

    Roster size per team comes from our league settings (assumed the same in mocks).
    """
    from app.api.valuation import _league_draft

    d = live.get(league_id)
    if d is None:
        raise HTTPException(404, f"No capture for league {league_id}")
    pks = _yahoo_pks()
    names = _player_names()
    n_drafted, _ = _league_draft()
    with live.lock:
        s = d.state
        picks = sorted(s.picks.values(), key=lambda p: p.pick_no)
        team_ids = sorted(set(d.team_names) | set(s.server_budgets) | set(s.nomination_order)
                          | {p.team_id for p in picks})
        slots = n_drafted // max(len(team_ids), 12)
        money_left = {t: s.money_left(t) for t in team_ids}
        open_slots = {t: max(slots - sum(1 for p in picks if p.team_id == t), 0) for t in team_ids}
        bids = money.max_bids(money_left, open_slots)
        n = s.nomination
        return {
            "league_id": league_id,
            "my_team_id": d.my_team_id,
            "budget": s.budget,
            "slots_per_team": slots,
            "last_event_at": _iso(d.last_event_at),
            "teams": [
                {"team_id": t, "name": d.team_names.get(t), "money_left": money_left[t], "spent": s.spent(t),
                 "open_slots": open_slots[t], "max_bid": bids[t], "mine": t == d.my_team_id,
                 "online": t in s.online, "autopick": t in s.autopick}
                for t in team_ids
            ],
            "picks": [
                {"pick_no": p.pick_no, "player_pk": pks.get(p.player_id), "yahoo_id": p.player_id,
                 "name": names.get(p.player_id),
                 "team_id": p.team_id, "price": p.price, "roster_slot": p.roster_slot}
                for p in picks
            ],
            "nomination": (
                {"player_pk": pks.get(n.player_id), "yahoo_id": n.player_id, "name": names.get(n.player_id),
                 "high_bid": n.high_bid,
                 "high_team_id": n.high_team_id, "nominating_team_id": n.nominating_team_id}
                if n else None
            ),
        }
