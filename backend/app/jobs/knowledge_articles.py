"""Articles (T-022, layer 3): plan, write, render.

Usage: python -m app.jobs.knowledge_articles [--replan] [--only a,b] [--parallel 6] [--render-only]
Make:  make knowledge-articles

Needs the player profiles and the knowledge_tags table (make knowledge-run first).
The plan is saved in docs/knowledge/_data/articles/_plan.json and reused until
--replan. Articles already written are rebuilt only with --only or --force.
Markdown goes to docs/knowledge/articles/.
"""

import argparse
import functools
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import REPO_ROOT
from app.db import SessionLocal, init_db
from app.experts import llm
from app.jobs import digest_experts as dx
from app.knowledge import articles, profile, render

print = functools.partial(print, flush=True)
OUT_DIR = REPO_ROOT / "docs" / "knowledge" / "articles"


def _f(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def article_md(doc: dict, rules: dict[str, articles.Rule], players: dict[str, articles.ArticlePlayer]) -> str:
    def src(ids):
        out = []
        for x in ids:
            if x.startswith("player:"):
                s = x.split(":", 1)[1]
                name = players[s].name if s in players else s
                out.append(f"[{name}](../profiles/players/{s}.md)")
            elif (r := rules.get(x)):
                out.append(f"[{r.date[5:]}]({r.url})")
        return ", ".join(out)

    out = [f"# {doc['title']}", ""]
    if doc.get("proposed"):
        out += ["<sub>Proposed by the synthesis, not on the user's list.</sub>", ""]
    out += [f"**Summary.** {render.escape_dollar(doc['summary'])}", ""]
    for s in doc["sections"]:
        out += [f"## {s['heading']}", ""]
        for p in s["paragraphs"]:
            out += [f"{render.escape_dollar(p['text'])} ({src(p['sources'])})", ""]
    if doc.get("players"):
        out += ["## Players", "", "Prices in USD. Yahoo and ESPN: rank and average auction cost for 2026-27.", ""]
        tiers: dict[str, list[dict]] = {}
        for p in doc["players"]:
            tiers.setdefault(p["tier"], []).append(p)
        for tier, ps in tiers.items():
            out += [f"### {tier}", "",
                    "| Player | Team | Pos | Yahoo rank | Yahoo cost | ESPN rank | ESPN cost | Our league 2025-26 | Why |",
                    "|---|---|---|---|---|---|---|---|---|"]
            for p in ps:
                a = players[p["slug"]]
                by = {x.source: x for x in a.numbers.prices}
                y, e = by.get("yahoo"), by.get("espn")
                out.append(f"| [{a.name}](../profiles/players/{a.slug}.md) | {a.team or 'FA'} | {a.position} | "
                           f"{y.rank if y and y.rank else '-'} | {_f(y and y.average_cost)} | "
                           f"{e.rank if e and e.rank else '-'} | {_f(e and e.average_cost)} | "
                           f"{a.numbers.league_price or 'not drafted'} | {render.escape_dollar(p['line'])} |")
            out.append("")
    if doc.get("excluded"):
        out += ["<details><summary>Left out</summary>", ""]
        out += [f"- {players[x['slug']].name if x['slug'] in players else x['slug']}: {x['reason']}"
                for x in doc["excluded"]]
        out += ["", "</details>", ""]
    if doc.get("rejected"):
        out.append(f"<sub>Paragraphs removed by the source check: {len(doc['rejected'])}.</sub>\n")
    out.append(f"<sub>Built {doc['built_at'][:10]} with {doc['llm'].get('model')} {doc['llm'].get('effort')}.</sub>\n")
    return "\n".join(out)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replan", action="store_true")
    ap.add_argument("--only", help="comma separated article slugs to (re)write")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--render-only", action="store_true")
    a = ap.parse_args(argv)

    init_db()
    rules = articles.collect_rules(dx.load_docs())
    rule_by_id = {r.id: r for r in rules}
    profiles = {d["player"]["pk"]: d for d in profile.load_all()}
    with SessionLocal() as db:
        counts = articles.tag_counts(db)
        if not counts:
            sys.exit("knowledge_tags is empty: run make knowledge-run first.")
        if a.replan or not articles.PLAN_FILE.exists():
            print(f"Planning from {len(rules)} method notes and {len(counts)} tags...")
            plan, _ = articles.plan(rules, counts)
            articles.DATA_DIR.mkdir(parents=True, exist_ok=True)
            articles.PLAN_FILE.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        plan = json.loads(articles.PLAN_FILE.read_text(encoding="utf-8"))
        items = plan["articles"]
        print(f"{len(items)} articles in the plan ({sum(1 for x in items if x['proposed'])} proposed).")
        inputs = {x["slug"]: ([rule_by_id[i] for i in x["rule_ids"] if i in rule_by_id],
                              articles.article_players(db, x["tags"], profiles) if x["tags"] else [])
                  for x in items}

    only = set(a.only.split(",")) if a.only else None
    done = {d["slug"] for d in articles.load_docs()}
    todo = [x for x in items if (only is None or x["slug"] in only)
            and (a.force or only or x["slug"] not in done)] if not a.render_only else []
    if todo:
        print(f"Writing {len(todo)} articles, {a.parallel} at once.")
        with ThreadPoolExecutor(max_workers=a.parallel) as pool:
            futs = {pool.submit(articles.write, x, *inputs[x["slug"]]): x for x in todo}
            for f in as_completed(futs):
                x = futs[f]
                try:
                    doc = f.result()
                except llm.UsageLimit as e:
                    print(f"Usage limit: {e}. Stopping; run again later.")
                    llm.kill_all()
                    break
                except Exception as e:
                    print(f"  FAILED {x['slug']}: {e}")
                    continue
                articles.save(doc)
                print(f"  {x['slug']}: {len(doc['sections'])} sections, {len(doc['players'])} players, "
                      f"{len(doc['rejected'])} paragraphs rejected")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.md"):
        f.unlink()
    docs = articles.load_docs()
    index = ["# Articles", "", "Generated by `make knowledge-articles`. Plan: `_data/articles/_plan.json`.", ""]
    for kind, label in ((False, "Requested"), (True, "Proposed by the synthesis")):
        index += [f"## {label}", ""]
        for d in docs:
            if bool(d.get("proposed")) == kind:
                players = {p.slug: p for p in inputs.get(d["slug"], ([], []))[1]}
                render.write(OUT_DIR / f"{d['slug']}.md", article_md(d, rule_by_id, players))
                index.append(f"- [{d['title']}]({d['slug']}.md) ({d['type']}): {d['brief']}")
        index.append("")
    render.write(OUT_DIR / "README.md", "\n".join(index))
    print(f"Rendered {len(docs)} articles to docs/knowledge/articles/.")


if __name__ == "__main__":
    main(sys.argv[1:])
