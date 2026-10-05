"""Data flow diagram of the own projection (T-025) with live freshness.

Fills backend/app/analytics/projection/flow_template.html with the age of every source (from
the refresh jobs: last successful run or newest data, see app/jobs/refresh.py), the knowledge
layer and the last report, and writes docs/modules/projection-flow.html.
When sources or the flow change, edit the template (user rule, 2026-10-05: keep this diagram
current). Published as an artifact; Claude republishes the file to the same URL
(docs/modules/projection.md has the link).

Run: make flow
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT
from app.db import SessionLocal, init_db
from app.jobs import refresh

TEMPLATE = Path(__file__).resolve().parents[1] / "analytics" / "projection" / "flow_template.html"
OUT = REPO_ROOT / "docs" / "modules" / "projection-flow.html"
CONTEXT = REPO_ROOT / "data" / "projection_context"
KNOWLEDGE = REPO_ROOT / "docs" / "knowledge"


def age(t: datetime | None, now: datetime) -> str:
    if t is None:
        return "never"
    h = (now - t).total_seconds() / 3600
    when = f"{h:.0f} h ago" if h < 48 else f"{h / 24:.0f} days ago"
    return f"{t:%m-%d %H:%M} ({when})"


def mtime(paths) -> datetime | None:
    times = [p.stat().st_mtime for p in paths]
    return datetime.fromtimestamp(max(times), UTC) if times else None


def main() -> Path:
    init_db()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        runs, data = refresh.last_runs(db), refresh.data_times(db)
    values = {}
    for name in list(refresh.JOBS) + list(refresh.MANUAL):
        t = refresh.fresh_at(runs[name]["last_ok"], data.get(name)) if name in refresh.JOBS else data.get(name)
        values[name] = age(t, now)
    videos = sorted((KNOWLEDGE / "videos").glob("*.md"))
    values["videos"] = f"{len(videos)} videos, newest note {age(mtime(videos), now)}"
    profiles = list((KNOWLEDGE / "profiles" / "players").glob("*.md"))
    values["profiles"] = f"{len(profiles)} player profiles, built {age(mtime(profiles), now)}"
    docs = [json.loads(p.read_text()) for p in CONTEXT.glob("*.json")]
    if docs:
        newest = max(datetime.fromisoformat(d["built_at"]) for d in docs)
        oldest = min(datetime.fromisoformat(d["built_at"]) for d in docs)
        versions = sorted({d.get("prompt_version") for d in docs})
        values["llm"] = f"{len(docs)} teams, prompt v{','.join(map(str, versions))}, oldest {age(oldest, now)}"
    else:
        values["llm"] = "never run"
    values["report"] = age(mtime([CONTEXT / "review" / "ALL.html"] if (CONTEXT / "review" / "ALL.html").exists() else []), now)
    values["generated"] = f"{now:%Y-%m-%d %H:%M}"
    html = TEMPLATE.read_text(encoding="utf-8")
    for k, v in values.items():
        html = html.replace("{{" + k + "}}", v)
    if "{{" in html:
        raise ValueError(f"unfilled slot in the template: {html[html.index('{{'):html.index('{{') + 40]}")
    OUT.write_text(html, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(f"Wrote {main()}")
