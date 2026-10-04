"""Static copy of the API for the GitHub Pages build.

Calls the real endpoints in process and writes their JSON under `OUT/api/`. The
frontend in static mode (`VITE_STATIC=1`) reads these files instead of the backend.

Valuation: every base, basis, model, dollars and pool, without punt. Player facts
(name, stats, market) go once per base; each combination stores only the numbers
that change: z per category, total, rank, dollars.

Usage: `uv run python -m app.jobs.export_static <out dir>`.
"""

import json
import os
import sys
from itertools import product
from pathlib import Path

os.environ["AUTO_REFRESH"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.analytics.valuation import CATEGORIES  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Player  # noqa: E402


def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(v, nd)


def main(out: Path) -> None:
    api = out / "api"
    c = TestClient(app)
    files = 0

    def get(path: str, **params) -> dict | list:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def write(rel: str, data) -> None:
        nonlocal files
        p = api / f"{rel}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        files += 1

    write("league", get("/api/league"))
    lives = get("/api/draft/live")
    write("draft/live", lives)
    for d in lives:
        write(f"draft/live/{d['league_id']}", get(f"/api/draft/live/{d['league_id']}"))

    opts = get("/api/valuation/options")
    write("valuation/options", opts)
    pools = [p or 0 for p in opts["pools"]]
    for b in opts["bases"]:
        base = f"{b['kind']}_{b['source']}_{b['season']}"
        facts = None
        for basis, model, dollars, pool in product(opts["basis"], [m["key"] for m in opts["models"]],
                                                   [d["key"] for d in opts["dollars"]], pools):
            v = get("/api/valuation", kind=b["kind"], source=b["source"], season=b["season"], basis=basis,
                    model=model, dollars=dollars, pool=pool)
            if facts is None:
                facts = [{k: p[k] for k in ("player_id", "nba_id", "name", "team", "positions", "injury", "stats", "usg_pct", "market")}
                         for p in v["players"]]
                write(f"valuation/{base}/players", facts)
            rows = [[p["player_id"], _r(p["total"]), p["rank"], _r(p["dollars"], 2),
                     *([_r(p["z"][k]) for k in CATEGORIES] if p["z"] else [None] * len(CATEGORIES))]
                    for p in v["players"]]
            write(f"valuation/{base}/{basis}_{model}_{dollars}_{pool}",
                  {"settings": v["settings"], "categories": list(CATEGORIES), "rows": rows})
        print(f"{base}: done", flush=True)

    teams: set[str] = set()
    # Every player, not only the valued ones: depth charts and articles link to the rest.
    with SessionLocal() as db:
        all_ids = sorted(db.scalars(select(Player.id)))
    for pk in all_ids:
        card = get(f"/api/players/{pk}/card")
        write(f"players/{pk}/card", card)
        write(f"knowledge/players/{pk}/tags", get(f"/api/knowledge/players/{pk}/tags"))
        if card["team"]:
            teams.add(card["team"])
    for t in sorted(teams):
        write(f"teams/{t}/depth", get(f"/api/teams/{t}/depth"))
    tags = get("/api/knowledge/tags", subject="player")
    write("knowledge/tags", tags)
    for t in tags:
        write(f"knowledge/tags/{t['tag']}", get(f"/api/knowledge/tags/{t['tag']}"))
    for f in sorted((Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "articles").glob("*.md")):
        if f.name != "README.md":
            write(f"knowledge/articles/{f.stem}", get(f"/api/knowledge/articles/{f.stem}"))
    print(f"{files} files in {api}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/public"))
