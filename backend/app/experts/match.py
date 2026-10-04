"""Map player and team names from notes to our players table and team codes.

The extraction prompt has no player list (too many tokens per call). The LLM
writes the real name it thinks of plus the name as said. Player matching order:
1. "alias": aliases.json "players", set by the user. Wins over the LLM's guess;
2. "exact": name_key of the LLM's full name, then of the name as said;
3. "learned": aliases.json "learned_players", nicknames the job learns from
   earlier matches (see learn_nicknames). Never sent to the LLM;
4. "fuzzy": same first initial and last name, or a close full-name spelling.
When a name fits more than one player ("Barnes"), the note's team decides; if
the team does not decide, there is no match. Fuzzy and learned matches are
listed on _unmatched.md for a check.

Matching runs at render time, so editing docs/knowledge/aliases.json and
re-rendering fixes a missed name without a new LLM call. Alias keys are
compared by name_key (no accents, punctuation, case or Jr/III suffix).
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Player
from app.sources.players.base import name_key
from app.sources.teams import canonical


@dataclass(frozen=True)
class KnownPlayer:
    name: str
    team: str | None
    key: str

    @property
    def slug(self) -> str:
        return self.key.replace(" ", "-")


def load_players(db: Session) -> list[KnownPlayer]:
    rows = db.execute(select(Player.first_name, Player.last_name, Player.team, Player.name_key)).all()
    return sorted((KnownPlayer(f"{f} {l}".strip(), t, k) for f, l, t, k in rows), key=lambda p: p.key)


def _key(name: str) -> str:
    return name_key(name or "", "")


class Matcher:
    def __init__(self, players: list[KnownPlayer], aliases: dict):
        self.by_key: dict[str, list[KnownPlayer]] = defaultdict(list)
        self.by_last: dict[str, list[KnownPlayer]] = defaultdict(list)
        for p in players:
            self.by_key[p.key].append(p)
            self.by_last[p.key.split()[-1]].append(p)
        self.user_aliases = {_key(a): _key(n) for a, n in aliases.get("players", {}).items()}
        self.learned_aliases = {_key(a): _key(n) for a, n in aliases.get("learned_players", {}).items()}
        self.team_aliases = {_key(a): t for a, t in aliases.get("teams", {}).items()}

    @staticmethod
    def _pick(cands: list[KnownPlayer], team: str | None) -> KnownPlayer | None:
        """The only candidate, or the only one on `team`. Else None."""
        if len(cands) == 1:
            return cands[0]
        on_team = [c for c in cands if team and c.team == team]
        return on_team[0] if len(on_team) == 1 else None

    def player(self, name: str, said_as: str = "", team: str = "") -> KnownPlayer | None:
        return self.player_how(name, said_as, team)[0]

    def player_how(self, name: str, said_as: str = "", team: str = "") -> tuple[KnownPlayer | None, str]:
        """(player, method). Method: "alias", "exact", "learned", "fuzzy" or "none"."""
        team = canonical(team)
        keys = [k for k in (_key(said_as), _key(name)) if k]
        for k in keys:
            if (p := self._pick(self.by_key.get(self.user_aliases.get(k, ""), []), team)):
                return p, "alias"
        for k in reversed(keys):  # the LLM's full name first
            if (p := self._pick(self.by_key.get(k, []), team)):
                return p, "exact"
        for k in keys:
            if (p := self._pick(self.by_key.get(self.learned_aliases.get(k, ""), []), team)):
                return p, "learned"
        for k in reversed(keys):
            words = k.split()
            if len(words) >= 2:
                cands = [c for c in self.by_last.get(words[-1], []) if c.key[0] == words[0][0]]
                if (p := self._pick(cands, team)):
                    return p, "fuzzy"
            close = get_close_matches(k, self.by_key, n=2, cutoff=0.88)
            if len(close) == 1 and (p := self._pick(self.by_key[close[0]], team)):
                return p, "fuzzy"
        return None, "none"

    def team(self, team: str) -> str | None:
        return canonical(team) or canonical(self.team_aliases.get(_key(team)))


def learn_nicknames(pairs: list[tuple[str, KnownPlayer]], min_count: int = 2) -> dict[str, str]:
    """Nicknames from (said_as, matched player) pairs of exact or fuzzy matches.

    A said_as is a nickname when it shares no word with the player's name
    ("Pencil", "Wemby"), is used at least `min_count` times, and always for
    the same player.
    """
    seen: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    shown: dict[str, str] = {}
    names: dict[str, str] = {}
    for said, p in pairs:
        k = _key(said)
        if not k or set(k.split()) & set(p.key.split()):
            continue
        seen[k][p.key] += 1
        shown.setdefault(k, said.strip())
        names[p.key] = p.name
    return {shown[k]: names[next(iter(v))] for k, v in sorted(seen.items())
            if len(v) == 1 and sum(v.values()) >= min_count}


def load_aliases(path: Path) -> dict:
    if not path.exists():
        return {"players": {}, "teams": {}}
    return json.loads(path.read_text(encoding="utf-8"))
