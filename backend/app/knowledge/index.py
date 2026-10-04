"""Lookups over the rendered knowledge pages for the player drawer (T-028).

Read on every call: `make knowledge-run` rewrites the files in place, and the
whole set is a few hundred small files.
"""

import json
import re
from pathlib import Path

from app.config import REPO_ROOT

KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge"
PROFILE_DATA_DIR = KNOWLEDGE_DIR / "_data" / "profiles" / "players"
PLAYER_MD_DIR = KNOWLEDGE_DIR / "profiles" / "players"
TEAM_MD_DIR = KNOWLEDGE_DIR / "profiles" / "teams"
ARTICLE_DIR = KNOWLEDGE_DIR / "articles"

# The only form of player link in the articles: ](../profiles/players/<slug>.md)
_PLAYER_LINK = re.compile(r"\]\((?:\.\./)*(?:profiles/)?players/([a-z0-9-]+)\.md\)")
_GENERATED = re.compile(r"^<!--.*?-->\s*", re.S)
_H1 = re.compile(r"^# (.+)$", re.M)


def player_slugs(profile_dir: Path = PROFILE_DATA_DIR) -> dict[str, int]:
    """Profile slug to player id, from the profile JSON (the id the profile was built for)."""
    out = {}
    for f in profile_dir.glob("*.json"):
        p = json.loads(f.read_text(encoding="utf-8"))["player"]
        out[p["slug"]] = p["pk"]
    return out


def article_index(slugs: dict[str, int], article_dir: Path = ARTICLE_DIR) -> dict[int, list[dict]]:
    """Player id to the articles that link to the player's profile, with the number of links."""
    out: dict[int, list[dict]] = {}
    for f in sorted(article_dir.glob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8")
        title = (m.group(1).strip() if (m := _H1.search(text)) else f.stem)
        counts: dict[int, int] = {}
        for slug in _PLAYER_LINK.findall(text):
            if (pk := slugs.get(slug)) is not None:
                counts[pk] = counts.get(pk, 0) + 1
        for pk, n in counts.items():
            out.setdefault(pk, []).append({"slug": f.stem, "title": title, "mentions": n})
    for arts in out.values():
        arts.sort(key=lambda a: -a["mentions"])
    return out


def for_drawer(md: str, slugs: dict[str, int]) -> str:
    """Page markdown for the drawer: no generator comment, no H1 (the drawer header has the name),
    player links as `#player/<id>` so the drawer opens that player. Unknown slugs lose the link."""
    md = _GENERATED.sub("", md, count=1)
    md = _H1.sub("", md, count=1).lstrip()

    def link(m: re.Match) -> str:
        pk = slugs.get(m.group(1))
        return f"](#player/{pk})" if pk is not None else "](#)"

    return _PLAYER_LINK.sub(link, md)


def read_page(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def article_path(slug: str) -> Path | None:
    """Article file for a slug, or None. The slug comes from a URL: only plain names pass."""
    if not re.fullmatch(r"[a-z0-9-]+", slug) or slug == "readme":
        return None
    p = ARTICLE_DIR / f"{slug}.md"
    return p if p.is_file() else None
