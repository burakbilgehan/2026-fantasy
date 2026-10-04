from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
# Schema of DBs made by create_all before Alembic was added (2026-10-03).
BASELINE_REVISION = "0001"
BASELINE_TABLES = {"leagues", "teams"}


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(exist_ok=True)
# SQLite: wait up to 30 s for a lock. The refresh thread and draft ingest write to one file.
engine = create_engine(get_settings().db_url, connect_args={"timeout": 30})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db(bind: Engine | None = None) -> None:
    """Bring the DB schema to the latest Alembic revision.

    A DB made by create_all has tables but no recorded revision. It is stamped
    first: at head when it already has every current table, else at baseline.
    """
    from alembic import command
    from alembic.config import Config

    from app import models  # noqa: F401  (register tables)

    with (bind or engine).begin() as conn:
        cfg = Config(str(ALEMBIC_INI))
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        versioned = "alembic_version" in tables and conn.execute(
            text("SELECT count(*) FROM alembic_version")
        ).scalar()
        if not versioned and BASELINE_TABLES <= tables:
            command.stamp(cfg, "head" if set(Base.metadata.tables) <= tables else BASELINE_REVISION)
        command.upgrade(cfg, "head")
