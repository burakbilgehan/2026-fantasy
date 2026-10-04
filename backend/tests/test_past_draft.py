import gzip
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.jobs.sync_past_draft import store
from app.models import Draft, DraftPick, DraftTeam

FIXTURES = Path(__file__).parent / "fixtures"


def _pages() -> dict[str, str]:
    return {
        p: gzip.decompress((FIXTURES / f"past_{p}.html.gz").read_bytes()).decode("utf-8")
        for p in ("settings", "standings", "draftresults")
    }


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    with Session(engine) as s:
        yield s


def test_store_is_idempotent(db):
    pages = _pages()
    store(db, 2025, "38073", pages)
    d = store(db, 2025, "38073", pages)
    assert db.scalar(select(func.count()).select_from(Draft)) == 1
    assert (d.kind, d.season, d.source, d.budget) == ("past_league", "2025-26", "yahoo_web", 200)
    picks = db.scalars(select(DraftPick).where(DraftPick.draft_pk == d.id)).all()
    assert len(picks) == 144
    teams = {t.team_id: t.name for t in db.scalars(select(DraftTeam).where(DraftTeam.draft_pk == d.id))}
    assert sorted(teams) == list(range(1, 13))
    by_team: dict[int, int] = {}
    for p in picks:
        by_team[p.team_id] = by_team.get(p.team_id, 0) + 1
    assert set(by_team.values()) == {12}
    jokic = next(p for p in picks if p.pick_no == 1)
    assert (teams[jokic.team_id], jokic.yahoo_player_id, jokic.price) == ("GOA Ta’biat Parki", "5352", 87)


def test_store_rejects_unknown_team(db):
    pages = _pages()
    pages["standings"] = pages["standings"].replace("Haydar Baş", "Someone Else")
    with pytest.raises(ValueError, match="Haydar"):
        store(db, 2025, "38073", pages)
