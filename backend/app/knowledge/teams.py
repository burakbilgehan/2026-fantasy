"""Team profiles (T-022): same structure as player profiles.

Numbers by code: win total line, games and back-to-backs for the season and for
our fantasy playoff weeks, Hashtag depth chart. Context: the team's players with
their profile tags. Notes: the team notes of layer 1.
Fantasy playoff weeks (RULES.md, verified): weeks 19 to 21, ending Sunday
2027-03-28, so Monday to Sunday 03-08..03-14, 03-15..03-21, 03-22..03-28.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.experts import llm
from app.experts.extract import no_em_dash
from app.knowledge import profile
from app.knowledge.profile import Note, _by_video, _load
from app.knowledge.tags import Registry
from app.models import DepthChartEntry as DepthChart, NbaGame as NbaSchedule, TeamWinTotal
from app.seasons import CURRENT_SEASON

PROMPT_DIR = REPO_ROOT / "prompts" / "knowledge_team"
TEAM_DIR = REPO_ROOT / "docs" / "knowledge" / "_data" / "profiles" / "teams"
CONFIG, SYSTEM, USER_PROMPT, SCHEMA, PROMPT_SHA = _load(PROMPT_DIR)
PLAYOFF_END = date(2027, 3, 28)
PLAYOFF_WEEKS = [(19, PLAYOFF_END - timedelta(days=20), PLAYOFF_END - timedelta(days=14)),
                 (20, PLAYOFF_END - timedelta(days=13), PLAYOFF_END - timedelta(days=7)),
                 (21, PLAYOFF_END - timedelta(days=6), PLAYOFF_END)]


@dataclass
class TeamNumbers:
    win_total: float | None
    win_rank: int | None
    games: int
    b2b: int
    b2b_rank: int  # 1 = fewest back-to-backs
    weeks: list[tuple[int, int, int]]  # (week, games, back-to-back pairs)
    playoff_games: int
    playoff_rank: int  # 1 = most games in weeks 19 to 21
    depth: list[str]


def _schedule(db: Session) -> dict[str, list[date]]:
    out: dict[str, list[date]] = {}
    for d, h, a in db.execute(select(NbaSchedule.game_date_et, NbaSchedule.home, NbaSchedule.away)
                              .where(NbaSchedule.season == CURRENT_SEASON)):
        out.setdefault(h, []).append(d)
        out.setdefault(a, []).append(d)
    return {t: sorted(ds) for t, ds in out.items()}


def _b2b(days: list[date]) -> int:
    return sum(1 for a, b in zip(days, days[1:]) if (b - a).days == 1)


def load_all(db: Session) -> dict[str, TeamNumbers]:
    sched = _schedule(db)
    wins = {t: w for t, w in db.execute(select(TeamWinTotal.team, TeamWinTotal.wins)
                                        .where(TeamWinTotal.season == CURRENT_SEASON))}
    b2b = {t: _b2b(ds) for t, ds in sched.items()}
    po = {t: sum(1 for d in ds if PLAYOFF_WEEKS[0][1] <= d <= PLAYOFF_END) for t, ds in sched.items()}
    out = {}
    for t, ds in sched.items():
        weeks = []
        for w, lo, hi in PLAYOFF_WEEKS:
            wd = [d for d in ds if lo <= d <= hi]
            weeks.append((w, len(wd), _b2b(wd)))
        depth = []
        rows = db.execute(select(DepthChart.slot, DepthChart.depth, DepthChart.player_name)
                          .where(DepthChart.team == t, DepthChart.season == CURRENT_SEASON)
                          .order_by(DepthChart.depth, DepthChart.slot, DepthChart.order)).all()
        for lvl in (1, 2):
            names = [f"{s} {n}" for s, d, n in rows if d == lvl]
            if names:
                depth.append(("Starters: " if lvl == 1 else "Second unit: ") + ", ".join(names))
        out[t] = TeamNumbers(
            wins.get(t), 1 + sum(1 for v in wins.values() if v > wins[t]) if t in wins else None,
            len(ds), b2b[t], 1 + sum(1 for v in b2b.values() if v < b2b[t]), weeks, po[t],
            1 + sum(1 for v in po.values() if v > po[t]), depth)
    return out


def numbers_md(n: TeamNumbers) -> str:
    weeks = " | ".join(f"{g} ({b})" for _, g, b in n.weeks)
    return "\n".join([
        "| Win total | Games | Back-to-backs | Week 19 | Week 20 | Week 21 | Playoff weeks total |",
        "|---|---|---|---|---|---|---|",
        f"| {n.win_total if n.win_total is not None else '-'} (rank {n.win_rank or '-'} of 30) | {n.games} | "
        f"{n.b2b} (rank {n.b2b_rank} of 30, 1 = fewest) | {weeks} | {n.playoff_games} (rank {n.playoff_rank} of 30) |",
        "",
        "Weeks: games (back-to-back pairs). Fantasy playoffs are weeks 19 to 21, ending 2027-03-28. "
        "Games = games scheduled so far (NBA Cup games are added later; a full season has 82).",
        "",
        *[f"- {line}" for line in n.depth],
    ])


def roster_context(team: str, player_docs: list[dict], reg: Registry) -> str:
    lines = []
    for d in player_docs:
        if d["player"]["team"] != team:
            continue
        names = []
        for t in d.get("tags", []):
            if reg.is_dropped(t["name"]):
                continue
            tag = reg.resolve(t["name"])
            names.append(tag.name if tag else t["name"])
        lines.append(f"- {d['player']['name']} ({d['player']['position']}): {', '.join(dict.fromkeys(names))}")
    return "\n".join(lines) or "None."


@dataclass
class TeamSubject:
    team: str
    notes: list[Note]
    numbers: TeamNumbers
    roster: str


def build_prompt(s: TeamSubject, reg: Registry) -> str:
    return USER_PROMPT.format(team=s.team, today=date.today().isoformat(), tag_list=reg.prompt_list(),
                              numbers=numbers_md(s.numbers), roster=s.roster, team_notes=_by_video(s.notes))


def input_sha(s: TeamSubject) -> str:
    import hashlib
    return hashlib.sha256(("\n".join(n.id for n in s.notes) + s.roster).encode()).hexdigest()[:12]


def run(s: TeamSubject, reg: Registry) -> dict:
    raw, usage = llm.run_json(build_prompt(s, reg), SYSTEM, SCHEMA, model=CONFIG["model"], effort=CONFIG["effort"])
    out, rejected = profile.check(no_em_dash(raw), {n.id for n in s.notes})
    return {"team": s.team, "prompt_version": CONFIG["prompt_version"], "prompt_sha": PROMPT_SHA,
            "input_sha": input_sha(s), "note_count": len(s.notes),
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"), "llm": usage, **out, "rejected": rejected}


def path(team: str):
    return TEAM_DIR / f"{team}.json"


def save(doc: dict) -> None:
    TEAM_DIR.mkdir(parents=True, exist_ok=True)
    path(doc["team"]).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_docs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TEAM_DIR.glob("*.json"))]
