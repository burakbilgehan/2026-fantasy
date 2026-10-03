"""Parse Yahoo draft room WebSocket messages into typed events.

Message meanings are documented in docs/modules/draft.md with their evidence
level. Unknown messages are kept as `Unknown` and do not change draft state.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OnTheClock:
    """`D|pick|team|sec`: team must nominate for pick number `pick`."""

    pick_no: int
    team_id: int
    seconds: int


@dataclass(frozen=True)
class Nomination:
    """`n|team|player|bid|sec`."""

    team_id: int
    player_id: str
    amount: int
    seconds: int


@dataclass(frozen=True)
class Bid:
    """`b|team|player|bid|sec`."""

    team_id: int
    player_id: str
    amount: int
    seconds: int


@dataclass(frozen=True)
class Sale:
    """`0|pick|player|team|slot|price`."""

    pick_no: int
    player_id: str
    team_id: int
    roster_slot: str
    price: int


@dataclass(frozen=True)
class Budgets:
    """`$|team=money|...`: money left per team, sent by the server."""

    money: dict[int, int]


@dataclass(frozen=True)
class PastPicks:
    """`P|pick=player,team,price|...`: all picks so far, sent on every connect."""

    picks: dict[int, tuple[str, int, int]]  # pick_no -> (player_id, team_id, price)


@dataclass(frozen=True)
class NominationOrder:
    """`I|team|team|...`."""

    team_ids: tuple[int, ...]


@dataclass(frozen=True)
class Presence:
    """`A|team=0/1|...`: who is in the room, sent on connect."""

    online: dict[int, bool]


@dataclass(frozen=True)
class Joined:
    """`J|team`."""

    team_id: int


@dataclass(frozen=True)
class Left:
    """`L|team`."""

    team_id: int


@dataclass(frozen=True)
class AutopickOn:
    """`5|team`: team timed out and the server now picks for it."""

    team_id: int


@dataclass(frozen=True)
class AutopickOff:
    """`6|team`."""

    team_id: int


@dataclass(frozen=True)
class Connected:
    """Extension saw a new WebSocket (`ws_open`). Live parts of the old state are stale."""


@dataclass(frozen=True)
class Unknown:
    kind: str
    raw: str


Event = (
    OnTheClock | Nomination | Bid | Sale | Budgets | PastPicks | NominationOrder
    | Presence | Joined | Left | AutopickOn | AutopickOff | Connected | Unknown
)


@dataclass(frozen=True)
class TimedEvent:
    """`at` is the backend receive time (`received_at`, UTC). Browser `ts` is not used."""

    at: datetime
    event: Event


def _team_map(items: list[str]) -> dict[int, int]:
    out = {}
    for item in items:
        team, value = item.split("=")
        out[int(team)] = int(value)
    return out


def parse_ws(body: str) -> Event:
    parts = body.split("|")
    kind, args = parts[0], parts[1:]
    try:
        match kind:
            case "D":
                return OnTheClock(int(args[0]), int(args[1]), int(args[2]))
            case "n":
                return Nomination(int(args[0]), args[1], int(args[2]), int(args[3]))
            case "b":
                return Bid(int(args[0]), args[1], int(args[2]), int(args[3]))
            case "0":
                return Sale(int(args[0]), args[1], int(args[2]), args[3], int(args[4]))
            case "$":
                return Budgets(_team_map(args))
            case "P":
                picks = {}
                for item in args:
                    pick_no, value = item.split("=")
                    player_id, team_id, price = value.split(",")
                    picks[int(pick_no)] = (player_id, int(team_id), int(price))
                return PastPicks(picks)
            case "I":
                return NominationOrder(tuple(int(a) for a in args))
            case "A":
                return Presence({t: v == 1 for t, v in _team_map(args).items()})
            case "J":
                return Joined(int(args[0]))
            case "L":
                return Left(int(args[0]))
            case "5":
                return AutopickOn(int(args[0]))
            case "6":
                return AutopickOff(int(args[0]))
    except (IndexError, ValueError):
        pass  # Malformed known message: keep it raw rather than crash the replay.
    return Unknown(kind, body)


def parse_capture_line(row: dict) -> TimedEvent | None:
    """Turn one capture JSON line into an event. Other rows (fetch, DOM) return None."""
    if row.get("kind") == "ws_open":
        return TimedEvent(datetime.fromisoformat(row["received_at"]), Connected())
    if row.get("kind") != "ws_message":
        return None
    body = row.get("data", {}).get("body")
    if not isinstance(body, str):
        return None
    return TimedEvent(datetime.fromisoformat(row["received_at"]), parse_ws(body))
