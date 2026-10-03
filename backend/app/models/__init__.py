from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class League(Base):
    """One row per league season. `league_id` is Yahoo's numeric id (23772)."""

    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    num_teams: Mapped[int]
    scoring_type: Mapped[str]
    draft_type: Mapped[str]
    draft_budget: Mapped[int | None]
    draft_time: Mapped[str | None]
    roster_positions: Mapped[list[str]] = mapped_column(JSON)
    stat_categories: Mapped[list[str]] = mapped_column(JSON)
    raw_settings: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str]  # "yahoo_api" or "yahoo_web"
    synced_at: Mapped[datetime]


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_pk: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    team_id: Mapped[int]  # Yahoo team number inside the league (1..12)
    name: Mapped[str]
