"""Live draft state, fed by the capture endpoint as extension events arrive.

One `LiveDraft` per league id, kept in memory. On first use after a backend
start it is rebuilt from the capture files (the source of truth), so a restart
mid-draft loses nothing. Every later row is applied incrementally.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.draft import capture
from app.draft.parser import Sale, parse_capture_line
from app.draft.state import DraftState, apply


@dataclass
class LiveDraft:
    league_id: str
    state: DraftState = field(default_factory=DraftState)
    team_names: dict[int, str] = field(default_factory=dict)
    my_team_id: int | None = None
    last_event_at: datetime | None = None  # Any WebSocket row, also `C|` (sent every 6 s).

    def feed(self, row: dict) -> bool:
        """Apply one capture row. Returns True when the row was a sale."""
        if self.my_team_id is None and (ids := capture.page_ids(row.get("url"))):
            self.my_team_id = ids[1]
        if row.get("kind") == "fetch":
            self._read_teams(row)
            return False
        te = parse_capture_line(row)
        if te is None:
            return False
        self.last_event_at = te.at
        apply(self.state, te)
        return isinstance(te.event, Sale)

    def _read_teams(self, row: dict) -> None:
        if "/fantasy/v3/teams/" not in row.get("data", {}).get("url", ""):
            return
        try:
            teams = json.loads(row["data"]["body"])["service"]["team_list"]
            self.team_names = {int(t["id"]): t["teamname"] for t in teams}
        except (KeyError, TypeError, ValueError):
            pass


lock = threading.RLock()  # Hold it while reading a LiveDraft too.
_drafts: dict[str, LiveDraft] = {}


def _load(league_id: str, base: Path) -> LiveDraft:
    draft = LiveDraft(league_id)
    for row in capture.iter_rows(league_id, base):
        draft.feed(row)
    return draft


def get(league_id: str, base: Path | None = None) -> LiveDraft | None:
    """The live draft for a league. Rebuilt from capture files on first use."""
    base = base or capture.CAPTURE_DIR
    with lock:
        if league_id not in _drafts:
            if not (base / league_id).is_dir():
                return None
            _drafts[league_id] = _load(league_id, base)
        return _drafts[league_id]


def feed(row: dict, base: Path | None = None) -> str | None:
    """Apply a row that was just written to the capture file.

    Returns the league id when the row was a sale (caller writes the DB), else None.
    """
    ids = capture.page_ids(row.get("url"))
    if ids is None:
        return None
    base = base or capture.CAPTURE_DIR
    with lock:
        draft = _drafts.get(ids[0])
        if draft is None:
            # First row of this league since start: the file already has it, so a full load covers it.
            _drafts[ids[0]] = _load(ids[0], base)
            return None
        return ids[0] if draft.feed(row) else None


def league_ids(base: Path | None = None) -> list[str]:
    return capture.league_ids(base or capture.CAPTURE_DIR)


def reset() -> None:
    """Drop all live state (tests)."""
    with lock:
        _drafts.clear()
