"""Common shape for player data sources.

A source turns one raw download into a list of SourcePlayer. The sync job
(`app.jobs.sync_players`) links each SourcePlayer to a `players` row and writes
its stat lines. Sources never touch the DB.
"""

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import RAW_DIR

# Stat line fields. Totals for the season, never per-game.
STAT_FIELDS = ("gp", "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")


@dataclass
class StatLine:
    season: str
    stats: dict[str, float]  # keys from STAT_FIELDS


@dataclass
class MarketValue:
    """Values the source itself publishes (not computed by us)."""

    season: str
    auction_value: float | None = None
    average_cost: float | None = None
    average_pick: float | None = None
    percent_drafted: float | None = None
    rank: int | None = None
    positions: list[str] | None = None
    injury: str | None = None
    injury_note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourcePlayer:
    external_id: str
    first_name: str
    last_name: str
    team: str | None  # canonical abbreviation (app.sources.teams), None = free agent
    position: str | None = None
    projection: StatLine | None = None
    actual: list[StatLine] = field(default_factory=list)
    market: MarketValue | None = None


class PlayerSource(Protocol):
    key: str  # stored in every row this source writes ("yahoo", "nba")
    label: str  # shown in the UI source picker
    provides: tuple[str, ...]  # subset of: "ids", "projections", "actual", "market"

    def fetch(self) -> Any:
        """Download and return the raw payload. Call save_raw() on it."""

    def parse(self, raw: Any, season: str) -> list[SourcePlayer]:
        """Pure. `season` is the season being drafted, like "2026-27"."""


def save_raw(key: str, payload: Any, suffix: str = "json") -> None:
    folder = RAW_DIR / key
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{int(time.time())}.{suffix}"
    if suffix == "json":
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(payload, encoding="utf-8")


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def name_key(first: str, last: str) -> str:
    """Match key: no accents, no punctuation, no Jr/III suffix, lower case."""
    s = unicodedata.normalize("NFKD", f"{first} {last}").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " "))
    return " ".join(_SUFFIX.sub("", s).split())
