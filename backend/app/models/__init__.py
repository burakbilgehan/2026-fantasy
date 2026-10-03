from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
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


class Draft(Base):
    """One auction draft seen by the extension (mock or the real league draft)."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    yahoo_league_id: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str]  # "league" when yahoo_league_id is our league, else "mock"
    my_team_id: Mapped[int | None]  # from the draft room URL
    budget: Mapped[int]
    source: Mapped[str]  # "extension"
    capture_dir: Mapped[str]
    first_event_at: Mapped[datetime | None]
    last_event_at: Mapped[datetime | None]
    ingested_at: Mapped[datetime]


class DraftTeam(Base):
    __tablename__ = "draft_teams"
    __table_args__ = (UniqueConstraint("draft_pk", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_pk: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"))
    team_id: Mapped[int]
    name: Mapped[str]


class DraftPick(Base):
    __tablename__ = "draft_picks"
    __table_args__ = (UniqueConstraint("draft_pk", "pick_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_pk: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"))
    pick_no: Mapped[int]
    team_id: Mapped[int]
    yahoo_player_id: Mapped[str]  # numeric Yahoo player id, as in "478.p.<id>"
    price: Mapped[int]
    roster_slot: Mapped[str | None]
    nominating_team_id: Mapped[int | None]
    sold_at: Mapped[datetime | None]  # None when known only from the reconnect replay
