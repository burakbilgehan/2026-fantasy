"""Alembic environment. The DB URL comes from app.config, not alembic.ini.

`app.db.init_db` runs migrations in-process and passes its connection through
`config.attributes["connection"]`. The `alembic` CLI uses the settings URL.
"""

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    # render_as_batch: SQLite cannot ALTER most things in place.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().db_url, target_metadata=target_metadata,
        literal_binds=True, render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with create_engine(get_settings().db_url).connect() as conn:
        _run(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
