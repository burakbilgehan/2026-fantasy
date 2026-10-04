"""Articles and compilations (T-022, layer 3).

1. Plan: one call reads all method notes and the tag counts, keeps the user's
   required list and proposes more articles (`proposed: true`).
2. Write: one call per article. Compilations get the players carrying the
   article's tags (from the DB copy of the tags, so after the category check).
   Player tables (prices, ranks) are printed by code.
3. Check: paragraphs keep only sources from their own input; players not in
   the input are dropped. Same idea as the profile source check.
Method notes get ids "{video_id}:r{i}" (i = index in the video's rules list).
Prompts: prompts/knowledge_article_plan/, prompts/knowledge_article/.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.experts import llm
from app.experts.extract import no_em_dash
from app.knowledge import stats
from app.knowledge.profile import _load
from app.models import KnowledgeTag

PLAN_CONFIG, PLAN_SYSTEM, PLAN_USER, PLAN_SCHEMA, PLAN_SHA = _load(REPO_ROOT / "prompts" / "knowledge_article_plan")
CONFIG, SYSTEM, USER_PROMPT, SCHEMA, PROMPT_SHA = _load(REPO_ROOT / "prompts" / "knowledge_article")
DATA_DIR = REPO_ROOT / "docs" / "knowledge" / "_data" / "articles"
PLAN_FILE = DATA_DIR / "_plan.json"

# User, 2026-10-04 (docs/modules/knowledge.md, "Articles and compilations").
REQUIRED = [
    "One compilation per punt build: punt FT%, punt AST, punt TO, and every other punt fit tag with at least 5 players.",
    "Breakout candidates (compilation).",
    "Bust candidates (compilation).",
    "Late-round flyers (compilation).",
    "Injury, shutdown and trade risk (compilation; may be split into separate lists).",
    "Auction tactics (topic): how to run a $200 live auction in our league.",
    "Strategy by draft stage (topic): early, middle and late in the auction.",
    "Do not draft by predicted injuries, except chronic cases (topic).",
    "Fantasy playoff weeks matter (topic): schedule for weeks 19 to 21, ending 2027-03-28.",
    "Weeks with 2 or 5 games for a team are outliers and need weekly lineup and streaming adjustments (topic).",
]


@dataclass
class Rule:
    id: str
    date: str
    text: str
    seconds: int | None

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id.split(':')[0]}?t={int(self.seconds or 0)}"


def collect_rules(docs: list[dict]) -> list[Rule]:
    out = []
    for doc in sorted(docs, key=lambda d: (d["video"]["upload_date"], d["video"]["id"]), reverse=True):
        for i, r in enumerate(doc.get("rules", [])):
            if r.get("verified"):
                out.append(Rule(f"{doc['video']['id']}:r{i}", doc["video"]["upload_date"], r["text"], r.get("seconds")))
    return out


def rules_text(rules: list[Rule]) -> str:
    return "\n".join(f"[{r.id}] {r.date}: {r.text}" for r in rules) or "None."


def tag_counts(db: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for (t,) in db.execute(select(KnowledgeTag.tag).where(KnowledgeTag.subject == "player")):
        out[t] = out.get(t, 0) + 1
    return out


def plan(rules: list[Rule], counts: dict[str, int]) -> tuple[dict, dict]:
    prompt = PLAN_USER.format(
        today=date.today().isoformat(), rule_count=len(rules),
        required="\n".join(f"- {r}" for r in REQUIRED),
        tag_counts="\n".join(f"- {t}: {n}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])),
        rules=rules_text(rules))
    raw, usage = llm.run_json(prompt, PLAN_SYSTEM, PLAN_SCHEMA, model=PLAN_CONFIG["model"], effort=PLAN_CONFIG["effort"])
    ids = {r.id for r in rules}
    raw = no_em_dash(raw)
    for a in raw["articles"]:
        a["rule_ids"] = [x for x in a["rule_ids"] if x in ids]
        a["tags"] = [t for t in a["tags"] if t in counts]
    return {"built_at": datetime.now(UTC).isoformat(timespec="seconds"), "prompt_sha": PLAN_SHA,
            "llm": usage, **raw}, usage


@dataclass
class ArticlePlayer:
    slug: str
    name: str
    team: str | None
    position: str | None
    pk: int
    tags: list[str]          # matching tags with detail
    note: str
    numbers: stats.PlayerNumbers

    def prompt_line(self) -> str:
        by = {p.source: p for p in self.numbers.prices}
        y, e = by.get("yahoo"), by.get("espn")
        price = (f"Yahoo rank {y.rank if y else '-'}, avg cost {y.average_cost if y else '-'}; "
                 f"ESPN rank {e.rank if e else '-'}, avg cost {e.average_cost if e else '-'}; "
                 f"our league last season {self.numbers.league_price or 'not drafted'}")
        return (f"[player:{self.slug}] {self.name} ({self.team or 'FA'}, {self.position}). {price}. "
                f"Tags: {'; '.join(self.tags)}. Profile note: {self.note}")


def article_players(db: Session, tag_names: list[str], profiles: dict[int, dict]) -> list[ArticlePlayer]:
    rows = db.scalars(select(KnowledgeTag).where(KnowledgeTag.subject == "player",
                                                 KnowledgeTag.tag.in_(tag_names))).all()
    by_pk: dict[int, list[str]] = {}
    for t in rows:
        by_pk.setdefault(t.player_pk, []).append(t.tag + (f" ({t.detail})" if t.detail else ""))
    out = []
    for pk, tg in by_pk.items():
        doc = profiles.get(pk)
        if doc is None:
            continue
        p = doc["player"]
        out.append(ArticlePlayer(p["slug"], p["name"], p["team"], p["position"], pk, tg, doc.get("note", ""),
                                 stats.load(db, pk)))
    return sorted(out, key=lambda a: min([x.rank for x in a.numbers.prices if x.rank] or [999]))


def write(article: dict, rules: list[Rule], players: list[ArticlePlayer]) -> dict:
    prompt = USER_PROMPT.format(title=article["title"], today=date.today().isoformat(), brief=article["brief"],
                                rules=rules_text(rules),
                                players="\n".join(p.prompt_line() for p in players) or "None.")
    raw, usage = llm.run_json(prompt, SYSTEM, SCHEMA, model=CONFIG["model"], effort=CONFIG["effort"])
    raw = no_em_dash(raw)
    ok = {r.id for r in rules} | {f"player:{p.slug}" for p in players}
    rejected = []
    for s in raw["sections"]:
        keep = []
        for para in s["paragraphs"]:
            para["sources"] = [x for x in para["sources"] if x in ok]
            (keep if para["sources"] else rejected).append(para)
        s["paragraphs"] = keep
    slugs = {p.slug for p in players}
    raw["players"] = [p for p in raw["players"] if p["slug"] in slugs]
    return {**article, "prompt_sha": PROMPT_SHA, "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "llm": usage, "player_slugs": sorted(slugs), **raw, "rejected": rejected}


def save(doc: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{doc['slug']}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_docs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA_DIR.glob("*.json"))
            if not p.name.startswith("_")]
