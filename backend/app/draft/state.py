"""Draft state built by replaying parsed WebSocket events. Pure, no I/O."""

from dataclasses import dataclass, field
from datetime import datetime

from app.draft.parser import (
    AutopickOff, AutopickOn, Bid, Budgets, Connected, Joined, Left, Nomination, NominationOrder,
    OnTheClock, PastPicks, Presence, Sale, TimedEvent, Unknown,
)


@dataclass
class Pick:
    pick_no: int
    player_id: str
    team_id: int
    price: int
    roster_slot: str | None = None  # Only `0|` has it. `P|` does not.
    nominating_team_id: int | None = None
    sold_at: datetime | None = None  # None when the pick is known only from `P|`.


@dataclass
class OpenNomination:
    pick_no: int | None
    player_id: str
    nominating_team_id: int | None
    high_bid: int
    high_team_id: int
    bids: list[tuple[datetime, int, int]] = field(default_factory=list)  # (at, team, amount)


@dataclass
class DraftState:
    budget: int = 200
    picks: dict[int, Pick] = field(default_factory=dict)
    nomination_order: tuple[int, ...] = ()
    on_the_clock: OnTheClock | None = None
    nomination: OpenNomination | None = None
    online: set[int] = field(default_factory=set)
    autopick: set[int] = field(default_factory=set)
    server_budgets: dict[int, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unknown: dict[str, int] = field(default_factory=dict)

    def spent(self, team_id: int) -> int:
        return sum(p.price for p in self.picks.values() if p.team_id == team_id)

    def money_left(self, team_id: int) -> int:
        return self.budget - self.spent(team_id)


def apply(state: DraftState, te: TimedEvent) -> DraftState:
    """Apply one event in place and return the state."""
    e = te.event
    match e:
        case OnTheClock():
            state.on_the_clock = e
            n = state.nomination
            if n is not None and n.pick_no is None:
                # Reconnect snapshot sends `b|` then `D|` for the open nomination (inferred).
                n.pick_no, n.nominating_team_id = e.pick_no, e.team_id
            else:
                state.nomination = None
        case Nomination():
            pick_no = state.on_the_clock.pick_no if state.on_the_clock else None
            state.nomination = OpenNomination(
                pick_no, e.player_id, e.team_id, e.amount, e.team_id, [(te.at, e.team_id, e.amount)]
            )
        case Bid():
            n = state.nomination
            if n is None:
                # On reconnect the server sends the current high bid without the `n|`.
                state.nomination = OpenNomination(
                    None, e.player_id, None, e.amount, e.team_id, [(te.at, e.team_id, e.amount)]
                )
            elif n.player_id != e.player_id:
                state.warnings.append(f"{te.at.isoformat()} bid for {e.player_id} during {n.player_id}")
            else:
                n.high_bid, n.high_team_id = e.amount, e.team_id
                n.bids.append((te.at, e.team_id, e.amount))
        case Sale():
            n = state.nomination
            nominator = n.nominating_team_id if n and n.player_id == e.player_id else None
            if n and n.player_id == e.player_id and (n.high_bid, n.high_team_id) != (e.price, e.team_id):
                state.warnings.append(
                    f"{te.at.isoformat()} sale {e.pick_no} differs from last bid "
                    f"({e.team_id} ${e.price} vs {n.high_team_id} ${n.high_bid})"
                )
            state.picks[e.pick_no] = Pick(
                e.pick_no, e.player_id, e.team_id, e.price, e.roster_slot, nominator, te.at
            )
            state.nomination = None
            if state.on_the_clock and state.on_the_clock.pick_no == e.pick_no:
                state.on_the_clock = None
        case PastPicks():
            for pick_no, (player_id, team_id, price) in e.picks.items():
                old = state.picks.get(pick_no)
                if old is None:
                    state.picks[pick_no] = Pick(pick_no, player_id, team_id, price)
                elif (old.player_id, old.team_id, old.price) != (player_id, team_id, price):
                    state.warnings.append(f"{te.at.isoformat()} replayed pick {pick_no} differs from live sale")
                    state.picks[pick_no] = Pick(pick_no, player_id, team_id, price)
        case Budgets():
            if not state.server_budgets and e.money:
                # First budget message fixes the auction budget (league setting, not in v3 settings).
                team_id, money = next(iter(e.money.items()))
                state.budget = money + state.spent(team_id)
            state.server_budgets = dict(e.money)
            for team_id, money in e.money.items():
                if state.money_left(team_id) != money:
                    state.warnings.append(
                        f"{te.at.isoformat()} team {team_id} budget: server ${money}, "
                        f"computed ${state.money_left(team_id)}"
                    )
        case NominationOrder():
            state.nomination_order = e.team_ids
        case Presence():
            state.online = {t for t, on in e.online.items() if on}
        case Joined():
            state.online.add(e.team_id)
        case Left():
            state.online.discard(e.team_id)
        case AutopickOn():
            state.autopick.add(e.team_id)
        case AutopickOff():
            state.autopick.discard(e.team_id)
        case Connected():
            # The server sends a fresh snapshot after connect. Picks and budgets stay.
            state.on_the_clock = None
            state.nomination = None
        case Unknown():
            state.unknown[e.kind] = state.unknown.get(e.kind, 0) + 1
    return state


def replay(events, budget: int = 200) -> DraftState:
    state = DraftState(budget=budget)
    for te in events:
        apply(state, te)
    return state
