"""One player profile: notes + numbers -> `claude -p` -> checked JSON.

Input notes get stable ids: "{video_id}:p{i}" for the i-th player note of a
video, "{video_id}:t{i}" for team notes. Every statement and tag of the answer
must cite ids from its own input (or "stats"); items without one valid source
are moved to `rejected` (the layer 2 analogue of the layer 1 quote check).
Everything sent to `claude -p` lives in prompts/knowledge_profile/.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import REPO_ROOT
from app.experts import llm
from app.experts.extract import no_em_dash
from app.experts.match import KnownPlayer, Matcher
from app.knowledge import categories, stats
from app.knowledge.tags import Registry
from app.seasons import CURRENT_SEASON

PROMPT_DIR = REPO_ROOT / "prompts" / "knowledge_profile"
TAGS_PROMPT_DIR = REPO_ROOT / "prompts" / "knowledge_tags"
PROFILE_DIR = REPO_ROOT / "docs" / "knowledge" / "_data" / "profiles" / "players"


def _load(d: Path) -> tuple[dict, str, str, dict, str]:
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    system = (d / "system.md").read_text(encoding="utf-8").strip()
    user = (d / "user_prompt.md").read_text(encoding="utf-8").strip()
    schema = json.loads((d / "schema.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256((system + user + json.dumps(schema, sort_keys=True)).encode()).hexdigest()[:12]
    return config, system, user, schema, sha


CONFIG, SYSTEM, USER_PROMPT, SCHEMA, PROMPT_SHA = _load(PROMPT_DIR)


@dataclass
class Note:
    id: str
    date: str
    video_title: str
    horizon: str
    text: str
    value_hint: str = ""
    seconds: int | None = None

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id.split(':')[0]}?t={int(self.seconds or 0)}"

    def line(self) -> str:
        v = f" Value: {self.value_hint.strip().rstrip('.')}." if self.value_hint else ""
        return f"[{self.id}] ({self.horizon}) {self.text}{v}"


def collect_notes(docs: list[dict], matcher: Matcher) -> tuple[dict[str, list[Note]], dict[str, list[Note]]]:
    """Verified notes per player slug and per team code, newest video first."""
    players: dict[str, list[Note]] = {}
    teams: dict[str, list[Note]] = {}
    for doc in sorted(docs, key=lambda d: (d["video"]["upload_date"], d["video"]["id"]), reverse=True):
        v = doc["video"]
        for i, n in enumerate(doc["player_notes"]):
            if not n.get("verified"):
                continue
            p = matcher.player(n["player"], n.get("said_as", ""), n.get("team", ""))
            if p:
                players.setdefault(p.slug, []).append(
                    Note(f"{v['id']}:p{i}", v["upload_date"], v["title"], n["horizon"], n["text"],
                         n.get("value_hint", ""), n.get("seconds")))
        for i, n in enumerate(doc["team_notes"]):
            if n.get("verified") and (t := matcher.team(n["team"])):
                teams.setdefault(t, []).append(
                    Note(f"{v['id']}:t{i}", v["upload_date"], v["title"], n["horizon"], n["text"], "", n.get("seconds")))
    return players, teams


def _by_video(notes: list[Note]) -> str:
    if not notes:
        return "None."
    out, last = [], None
    for n in notes:
        if (n.date, n.video_title) != last:
            out.append(f"\n{n.date}, \"{n.video_title}\"")
            last = (n.date, n.video_title)
        out.append(n.line())
    return "\n".join(out).strip()


@dataclass
class Subject:
    player: KnownPlayer
    pk: int
    position: str | None
    notes: list[Note]
    team_notes: list[Note]
    numbers: stats.PlayerNumbers
    cats: categories.Profile | None = None

    def gate(self, rule: str, sources: list[str]) -> tuple[bool, str]:
        return categories.allowed(rule, self.cats, self.numbers.injury, sources)


def build_prompt(s: Subject, reg: Registry, today: str | None = None) -> str:
    team = s.player.team or "free agent"
    return USER_PROMPT.format(
        name=s.player.name, team=team, position=s.position or "?", today=today or date.today().isoformat(),
        season=CURRENT_SEASON, tag_list=reg.prompt_list(),
        stat_table=stats.stat_table(s.numbers), price_table=stats.price_table(s.numbers),
        injury=s.numbers.injury or "none",
        groups=", ".join(s.cats.groups) if s.cats else "?",
        category_profile=s.cats.prompt_block() if s.cats else "No projection, so no category profile. Use no category tags.",
        player_notes=_by_video(s.notes), team_notes=_by_video(s.team_notes),
    )


def check(out: dict, valid_ids: set[str]) -> tuple[dict, list[dict]]:
    """Keep only cited sources that exist. Items left with no source are rejected."""
    rejected = []
    ok_ids = valid_ids | {"stats"}
    for section in ("current", "durable", "tags"):
        keep = []
        for item in out.get(section, []):
            given = item.get("sources", [])
            good = [x for x in given if x in ok_ids]
            if len(good) < len(given):
                item["bad_sources"] = [x for x in given if x not in ok_ids]
            item["sources"] = good
            if good:
                keep.append(item)
            else:
                rejected.append({"section": section, **item})
        out[section] = keep
    return out, rejected


def input_sha(s: Subject) -> str:
    """Hash of the notes the profile was built from (numbers are rendered by code)."""
    ids = [n.id for n in s.notes] + [n.id for n in s.team_notes]
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12]


def run(s: Subject, reg: Registry, model: str = CONFIG["model"], effort: str = CONFIG["effort"]) -> dict:
    raw, usage = llm.run_json(build_prompt(s, reg), SYSTEM, SCHEMA, model=model, effort=effort)
    out, rejected = check(no_em_dash(raw), {n.id for n in s.notes} | {n.id for n in s.team_notes})
    return {
        "player": {"name": s.player.name, "slug": s.player.slug, "pk": s.pk, "team": s.player.team,
                   "position": s.position},
        "prompt_version": CONFIG["prompt_version"],
        "prompt_sha": PROMPT_SHA,
        "input_sha": input_sha(s),
        "note_count": len(s.notes),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "llm": usage,
        **out,
        "rejected": rejected,
    }


def path(slug: str) -> Path:
    return PROFILE_DIR / f"{slug}.json"


def save(doc: dict) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path(doc["player"]["slug"]).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_all() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROFILE_DIR.glob("*.json"))]


# --- tag classifier -------------------------------------------------------------

T_CONFIG, T_SYSTEM, T_USER, T_SCHEMA, T_SHA = _load(TAGS_PROMPT_DIR)


def unknown_tags(profiles: list[dict], reg: Registry) -> dict[str, list[dict]]:
    """Raw tag names the registry does not know -> their uses."""
    out: dict[str, list[dict]] = {}
    for doc in profiles:
        for t in doc.get("tags", []):
            if not reg.known(t["name"]):
                who = doc["player"]["name"] if "player" in doc else f"team {doc['team']}"
                out.setdefault(t["name"], []).append({"player": who, **t})
    return out


def classify(unknown: dict[str, list[dict]], reg: Registry) -> tuple[list[dict], dict]:
    lines = []
    for name, uses in sorted(unknown.items(), key=lambda kv: kv[0].lower()):
        meaning = next((u["new_meaning"] for u in uses if u.get("new_meaning")), "")
        channel = uses[0].get("channel", "")
        ex = "; ".join(f"{u['player']}: {u.get('detail') or '-'}" for u in uses[:8])
        lines.append(f'- {name} ({channel}) "{meaning}". Uses: {ex}')
    prompt = T_USER.format(tag_list=reg.prompt_list(), proposals="\n".join(lines))
    raw, usage = llm.run_json(prompt, T_SYSTEM, T_SCHEMA, model=T_CONFIG["model"], effort=T_CONFIG["effort"])
    return no_em_dash(raw)["decisions"], usage
