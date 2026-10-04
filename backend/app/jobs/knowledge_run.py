"""Expert knowledge synthesis run (T-022): player profiles, tag classifier, render.

Usage: python -m app.jobs.knowledge_run [--players a,b] [--parallel 6] [--force]
                                        [--render-only] [--combined PATH]
Make:  make knowledge-run   (all selected players)

Selection (user, 2026-10-04): Yahoo or ESPN rank within the top 250, plus every
player with at least 3 notes (331 players; 13 of them have no notes and get a
profile from the numbers only).
--players takes slugs ("kawhi-leonard"). A profile is rebuilt only when its
input notes or the prompt version changed, or with --force.
After the profiles: unknown tag names go to the classifier in chunks, the
registry (docs/knowledge/_data/tags.json) and the glossary tag section are
updated, then all profiles are rendered to docs/knowledge/profiles/.
"""

import argparse
import functools
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import REPO_ROOT
from app.db import SessionLocal, init_db
from app.experts import match
from app.jobs import digest_experts as dx
from app.knowledge import categories, profile, render, stats, tags, teams
from app.models import KnowledgeTag, Player, PlayerMarketValue
from app.seasons import CURRENT_SEASON

print = functools.partial(print, flush=True)

OUT_DIR = REPO_ROOT / "docs" / "knowledge" / "profiles"
DECISIONS_LOG = REPO_ROOT / "docs" / "knowledge" / "_data" / "tag_decisions.jsonl"
TOP_RANK = 250
MIN_NOTES = 3
CLASSIFY_CHUNK = 60


def subjects(db, known, notes, team_notes) -> dict[str, profile.Subject]:
    """All players with notes, plus top ranked players without notes, keyed by slug.

    A top ranked player without notes gets a profile from the numbers only
    (user, 2026-10-04: all 331 selected players get a profile).
    """
    by_slug = {p.slug: p for p in known}
    top_keys = set(db.scalars(select(Player.name_key).join(
        PlayerMarketValue, PlayerMarketValue.player_pk == Player.id).where(
        PlayerMarketValue.season == CURRENT_SEASON, PlayerMarketValue.rank <= TOP_RANK)))
    notes = {**{p.slug: [] for p in known if p.key in top_keys}, **notes}
    pool = categories.load_pool(db)
    out = {}
    for slug, ns in notes.items():
        kp = by_slug[slug]
        rows = db.execute(select(Player.id, Player.team, Player.position).where(Player.name_key == kp.key)).all()
        row = next((r for r in rows if r.team == kp.team), rows[0])
        yahoo = db.scalar(select(PlayerMarketValue.positions).where(
            PlayerMarketValue.player_pk == row.id, PlayerMarketValue.source == "yahoo",
            PlayerMarketValue.season == CURRENT_SEASON))
        pos = ",".join(yahoo) if yahoo else row.position
        raw = categories.per_game_projection(db, row.id)
        cats = pool.profile(row.id, raw, [g for g in ("G", "F", "C") if g in (yahoo or [])] or None) if raw else None
        out[slug] = profile.Subject(kp, row.id, pos, ns, team_notes.get(kp.team, []), stats.load(db, row.id), cats)
    return out


def selected(subs: dict[str, profile.Subject]) -> list[str]:
    def top(s):
        return any(p.rank and p.rank <= TOP_RANK for p in s.numbers.prices)
    return sorted(slug for slug, s in subs.items() if top(s) or len(s.notes) >= MIN_NOTES)


def needs_build(s: profile.Subject) -> bool:
    p = profile.path(s.player.slug)
    if not p.exists():
        return True
    old = json.loads(p.read_text(encoding="utf-8"))
    return (old.get("input_sha") != profile.input_sha(s)
            or old.get("prompt_version") not in profile.CONFIG["compatible_versions"])


def build(todo: list, reg: tags.Registry, parallel: int, run=profile.run, save=profile.save,
          name=lambda s: s.player.slug, config=profile.CONFIG) -> None:
    """Run the LLM step for each subject in parallel; one failure does not stop the run."""
    if not todo:
        return
    print(f"Building {len(todo)} profiles, {parallel} at once, {config['model']} {config['effort']}.")
    t0, cost, done = time.monotonic(), 0.0, 0
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futs = {pool.submit(run, s, reg): s for s in todo}
        for f in as_completed(futs):
            s = futs[f]
            try:
                doc = f.result()
            except profile.llm.UsageLimit as e:
                print(f"Usage limit: {e}. Stopping; run again later (done profiles are kept).")
                profile.llm.kill_all()
                break
            except Exception as e:
                print(f"  FAILED {name(s)}: {e}")
                continue
            save(doc)
            done += 1
            cost += doc["llm"].get("cost_usd_list") or 0
            print(f"  [{done}/{len(todo)}] {name(s)}: {len(doc['current'])} current, "
                  f"{len(doc['durable'])} durable, {len(doc['tags'])} tags, {len(doc['rejected'])} rejected "
                  f"({doc['llm'].get('duration_ms', 0) / 1000:.0f} s)")
    print(f"Profiles done in {time.monotonic() - t0:.0f} s, list price ${cost:.2f} (not billed).")


def team_subjects(db, team_notes, reg) -> dict[str, teams.TeamSubject]:
    nums = teams.load_all(db)
    pdocs = profile.load_all()
    return {t: teams.TeamSubject(t, team_notes.get(t, []), n, teams.roster_context(t, pdocs, reg))
            for t, n in nums.items()}


def team_needs_build(s: teams.TeamSubject) -> bool:
    p = teams.path(s.team)
    if not p.exists():
        return True
    old = json.loads(p.read_text(encoding="utf-8"))
    return (old.get("input_sha") != teams.input_sha(s)
            or old.get("prompt_version") not in teams.CONFIG["compatible_versions"])


def render_teams(tsubs: dict[str, teams.TeamSubject], reg: tags.Registry, notes: dict) -> None:
    (OUT_DIR / "teams").mkdir(parents=True, exist_ok=True)
    rows = []
    for doc in teams.load_docs():
        s = tsubs.get(doc["team"])
        if s is None:
            continue
        render.write(OUT_DIR / "teams" / f"{doc['team']}.md",
                     render.team_md(doc, teams.numbers_md(s.numbers), reg, notes))
        rt = render.resolved_tags(doc, reg, gate=lambda rule, sources: (False, "player tag"))
        for ch in ("current", "durable"):
            rows += [tag_row("team", e, ch, doc["built_at"], team=doc["team"]) for e in rt[ch]]
    replace_tags("team", rows)
    print(f"Rendered {len(tsubs)} team profiles.")


def classify_all(reg: tags.Registry) -> list[str]:
    log = []
    while True:
        unknown = profile.unknown_tags(profile.load_all() + teams.load_docs(), reg)
        if not unknown:
            break
        chunk = dict(sorted(unknown.items(), key=lambda kv: -len(kv[1]))[:CLASSIFY_CHUNK])
        print(f"Classifying {len(chunk)} of {len(unknown)} unknown tag names...")
        decisions, usage = profile.classify(chunk, reg)
        lines = tags.apply_decisions(reg, [d for d in decisions if d["proposal"] in chunk])
        missing = [n for n in chunk if not reg.known(n)]
        with DECISIONS_LOG.open("a", encoding="utf-8") as f:
            for d in decisions:
                f.write(json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds"),
                                    "prompt_sha": profile.T_SHA, **d}, ensure_ascii=False) + "\n")
        log += lines
        reg.save()
        if missing:  # the classifier skipped or failed some names: do not loop forever
            log += [f"unresolved: {n}" for n in missing]
            break
    tags.write_glossary(reg)
    return log


def tag_row(subject: str, e: dict, channel: str, built_at: str, player_pk: int | None = None,
            team: str | None = None) -> KnowledgeTag:
    return KnowledgeTag(subject=subject, player_pk=player_pk, team=team, tag=e["name"], raw_name=e["raw"],
                        kind=e["kind"], channel=channel, detail=e["detail"] or None, until=e["until"] or None,
                        sources=e["sources"], classified=not e["unclassified"],
                        built_at=datetime.fromisoformat(built_at))


def replace_tags(subject: str, rows: list[KnowledgeTag]) -> None:
    """The DB copy of the tags for one subject type. JSON stays the source of truth."""
    with SessionLocal() as db, db.begin():
        db.query(KnowledgeTag).filter(KnowledgeTag.subject == subject).delete()
        db.add_all(rows)


def render_all(subs: dict[str, profile.Subject], reg: tags.Registry, combined: str | None,
               only: list[str] | None) -> None:
    notes = {n.id: n for s in subs.values() for n in s.notes + s.team_notes}
    docs = {d["player"]["slug"]: d for d in profile.load_all()}
    (OUT_DIR / "players").mkdir(parents=True, exist_ok=True)
    for f in (OUT_DIR / "players").glob("*.md"):
        f.unlink()
    users: dict[str, list[str]] = {}
    rows: list[KnowledgeTag] = []
    for slug, doc in docs.items():
        s = subs.get(slug)
        if s is None:
            continue
        render.write(OUT_DIR / "players" / f"{slug}.md", render.profile_md(
            doc, s.numbers, reg, notes, gate=s.gate, category_block=s.cats.prompt_block() if s.cats else ""))
        rt = render.resolved_tags(doc, reg, s.gate)
        for ch in ("current", "durable"):
            for e in rt[ch]:
                users.setdefault(e["name"], []).append(f"[{s.player.name}](players/{slug}.md)")
                rows.append(tag_row("player", e, ch, doc["built_at"], player_pk=s.pk))
    replace_tags("player", rows)
    lines = ["# Tags", "", "Players per tag. Meanings: `docs/GLOSSARY.md`, section Tags.", ""]
    for t in sorted(users, key=lambda n: (-len(users[n]), n.lower())):
        mark = "" if reg.resolve(t) else " (unclassified)"
        lines.append(f"- **{t}**{mark} ({len(users[t])}): {', '.join(sorted(users[t]))}")
    render.write(OUT_DIR / "tags.md", "\n".join(lines) + "\n")
    if combined:
        order = only or sorted(docs)
        parts = [render.profile_md(docs[s], subs[s].numbers, reg, notes, level=2, gate=subs[s].gate,
                                   category_block=subs[s].cats.prompt_block() if subs[s].cats else "")
                 for s in order if s in docs and s in subs]
        path = REPO_ROOT / combined
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# T-022 pilot: profiles from the pipeline\n\n"
                        "Generated by `make knowledge-run`. Compare with `profiles-demo.md` (hand-written).\n\n---\n\n"
                        + "\n---\n\n".join(parts), encoding="utf-8")
    print(f"Rendered {len(docs)} profiles to {OUT_DIR.relative_to(REPO_ROOT)}.")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", help="comma separated slugs; default: the selection")
    ap.add_argument("--skip-players", action="store_true", help="no player LLM step")
    ap.add_argument("--teams", action="store_true", help="also build the 30 team profiles (after the players)")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--combined", help="also write all rendered profiles to one file (repo relative path)")
    a = ap.parse_args(argv)

    init_db()
    known = dx.players()
    matcher = match.Matcher(known, match.load_aliases(dx.ALIASES))
    notes, team_notes = profile.collect_notes(dx.load_docs(), matcher)
    with SessionLocal() as db:
        subs = subjects(db, known, notes, team_notes)
    reg = tags.Registry.load()
    only = [x.strip() for x in a.players.split(",")] if a.players else None
    if only and (bad := [x for x in only if x not in subs]):
        sys.exit(f"No notes for: {', '.join(bad)}")
    slugs = only or selected(subs)
    print(f"{len(slugs)} players selected ({len(subs)} candidates).")
    if not a.render_only and not a.skip_players:
        todo = [subs[s] for s in slugs if a.force or needs_build(subs[s])]
        build(todo, reg, a.parallel)
        for line in classify_all(reg):
            print("  tag " + line)
    render_all(subs, reg, a.combined, only)
    with SessionLocal() as db:
        tsubs = team_subjects(db, team_notes, reg)
    if a.teams and not a.render_only:
        todo = [s for s in tsubs.values() if a.force or team_needs_build(s)]
        build(todo, reg, a.parallel, run=teams.run, save=teams.save, name=lambda s: s.team, config=teams.CONFIG)
        for line in classify_all(reg):
            print("  tag " + line)
        render_all(subs, reg, None, None)  # team tag merges can touch player tags too
    tnotes = {n.id: n for ns in team_notes.values() for n in ns}
    render_teams(tsubs, reg, tnotes)


if __name__ == "__main__":
    main(sys.argv[1:])
