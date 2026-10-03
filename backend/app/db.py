from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, get_settings


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(exist_ok=True)
engine = create_engine(get_settings().db_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
