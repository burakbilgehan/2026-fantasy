"""Tag registry: one canonical name per meaning, with aliases.

Profiles store the tag name the LLM wrote. The registry maps that raw name to a
canonical tag at read time, so a merge (alias added) fixes every profile at once
without a rewrite. Names the registry does not know go to the classifier
(`classify`), which merges each one into an existing tag, creates a new tag, or
drops it (not useful as a filter). File: docs/knowledge/_data/tags.json.
The tag section of docs/GLOSSARY.md is generated from it.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPO_ROOT

TAGS_FILE = REPO_ROOT / "docs" / "knowledge" / "_data" / "tags.json"
GLOSSARY = REPO_ROOT / "docs" / "GLOSSARY.md"
GLOSSARY_START = "<!-- tags:start (generated from docs/knowledge/_data/tags.json, do not edit) -->"
GLOSSARY_END = "<!-- tags:end -->"
KIND_ORDER = ["category role", "build fit", "role", "outlook", "risk", "health", "market",
              "schedule", "expert call"]


def key(name: str) -> str:
    """Compare tag names without case, hyphens or extra spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", name or "")).strip().lower()


@dataclass
class Tag:
    name: str
    meaning: str
    kind: str
    channel: str
    aliases: list[str] = field(default_factory=list)
    rule: str | None = None  # code check, see knowledge.categories.allowed; None = no check


class Registry:
    def __init__(self, tags: list[Tag], dropped: list[str]):
        self.tags = tags
        self.dropped = dropped
        self._index()

    def _index(self) -> None:
        self.by_key: dict[str, Tag] = {}
        for t in self.tags:
            for n in (t.name, *t.aliases):
                self.by_key[key(n)] = t
        self.dropped_keys = {key(d) for d in self.dropped}

    @classmethod
    def load(cls, path: Path = TAGS_FILE) -> "Registry":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([Tag(**t) for t in raw["tags"]], raw.get("dropped", []))

    def save(self, path: Path = TAGS_FILE) -> None:
        tags = sorted(self.tags, key=lambda t: (KIND_ORDER.index(t.kind) if t.kind in KIND_ORDER
                                                else len(KIND_ORDER), t.name.lower()))
        lines = ",\n".join("    " + json.dumps(t.__dict__, ensure_ascii=False) for t in tags)
        path.write_text('{\n  "tags": [\n' + lines + '\n  ],\n  "dropped": '
                        + json.dumps(sorted(set(self.dropped), key=str.lower), ensure_ascii=False)
                        + "\n}\n", encoding="utf-8")

    def resolve(self, raw: str) -> Tag | None:
        return self.by_key.get(key(raw))

    def is_dropped(self, raw: str) -> bool:
        return key(raw) in self.dropped_keys

    def known(self, raw: str) -> bool:
        return self.resolve(raw) is not None or self.is_dropped(raw)

    def add_alias(self, target: str, alias: str) -> None:
        t = self.resolve(target)
        if t is None:
            raise KeyError(target)
        if key(alias) != key(t.name) and key(alias) not in {key(a) for a in t.aliases}:
            t.aliases.append(alias)
        self._index()

    def add_tag(self, tag: Tag) -> Tag:
        if (old := self.resolve(tag.name)):
            return old
        self.tags.append(tag)
        self._index()
        return tag

    def drop(self, raw: str) -> None:
        if not self.known(raw):
            self.dropped.append(raw)
            self._index()

    def prompt_list(self) -> str:
        """Tag list for the profile prompt, grouped by kind."""
        out = []
        for kind in KIND_ORDER + sorted({t.kind for t in self.tags} - set(KIND_ORDER)):
            group = [t for t in self.tags if t.kind == kind]
            if group:
                out.append(f"{kind}:")
                out += [f"- {t.name} [{t.channel}]: {t.meaning}" for t in sorted(group, key=lambda t: t.name.lower())]
        return "\n".join(out)

    def glossary_section(self) -> str:
        out = [GLOSSARY_START, "## Tags",
               "Canonical tag names for profiles (T-022). Other names in brackets are merged into the tag.",
               "Code checks (`app/knowledge/categories.py`): `strong:X` = z >= 2.0 against the top 250 pool, "
               "`weak:X` = z <= -1.5 against the pool, `posweak:X` = z <= -1.0 against players of the same position, one of his two weakest categories, and positive value without it "
               "(a guard with few blocks is not a punt BLK fit), `bigstrong:X` = F or C with z >= 1.5 against the position, "
               "`no3pm` = under 0.3 threes per game, `noweak` = no weak flag at all, `injury` = Yahoo injury status or a note. "
               "Basis: 2026-27 projections per game (mean of Yahoo and ESPN); FG% and FT% as volume-weighted impact.", ""]
        for kind in KIND_ORDER + sorted({t.kind for t in self.tags} - set(KIND_ORDER)):
            group = sorted((t for t in self.tags if t.kind == kind), key=lambda t: t.name.lower())
            if not group:
                continue
            out.append(f"### {kind.capitalize()}")
            for t in group:
                al = f" (merged: {', '.join(t.aliases)})" if t.aliases else ""
                rule = f" Code check: `{t.rule}`." if t.rule else ""
                out.append(f"- **{t.name}** [{t.channel}]: {t.meaning}{rule}{al}")
            out.append("")
        out.append(GLOSSARY_END)
        return "\n".join(out)


def write_glossary(reg: Registry, path: Path = GLOSSARY) -> None:
    text = path.read_text(encoding="utf-8")
    section = reg.glossary_section()
    if GLOSSARY_START in text:
        head, rest = text.split(GLOSSARY_START, 1)
        tail = rest.split(GLOSSARY_END, 1)[1]
        text = head + section + tail
    else:
        text = text.rstrip() + "\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8")


def apply_decisions(reg: Registry, decisions: list[dict]) -> list[str]:
    """Apply classifier output. Returns a log line per decision.

    New tags first, so a merge can point at a tag created in the same batch.
    A merge into an unknown target leaves the name unresolved (next run retries).
    """
    log = []
    for d in decisions:
        if d["action"] == "new":
            target = d.get("target") or d["proposal"]
            t = reg.add_tag(Tag(target, d.get("meaning", ""), d.get("kind", "other"),
                                d.get("channel", "current")))
            if key(d["proposal"]) != key(t.name):
                reg.add_alias(t.name, d["proposal"])
            log.append(f"new: {d['proposal']} -> {t.name}")
    for d in decisions:
        if d["action"] == "merge":
            if reg.resolve(d.get("target", "")) is None:
                log.append(f"unresolved: {d['proposal']} (merge target {d.get('target')!r} unknown)")
                continue
            reg.add_alias(d["target"], d["proposal"])
            log.append(f"merge: {d['proposal']} -> {reg.resolve(d['target']).name}")
        elif d["action"] == "drop":
            reg.drop(d["proposal"])
            log.append(f"drop: {d['proposal']} ({d.get('reason', '')})")
    return log
