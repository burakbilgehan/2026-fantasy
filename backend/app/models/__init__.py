from datetime import date, datetime

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
    """One auction draft: seen by the extension (mock or our league), or a past league season
    read from the public draftresults page."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    yahoo_league_id: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str]  # "league" (our league), "mock", or "past_league" (earlier season)
    season: Mapped[str | None]  # "2025-26"; league ids are per season
    my_team_id: Mapped[int | None]  # from the draft room URL
    budget: Mapped[int]
    source: Mapped[str]  # "extension" or "yahoo_web"
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


class Player(Base):
    """One row per real player. Identity only; source ids are in player_external_ids."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    name_key: Mapped[str] = mapped_column(index=True)  # sources.players.base.name_key
    team: Mapped[str | None]  # canonical abbreviation, None = free agent
    position: Mapped[str | None]
    identity_source: Mapped[str]  # source that last set name, team, position
    updated_at: Mapped[datetime]


class PlayerExternalId(Base):
    """A player's id in one source. A new source adds rows here, never a column."""

    __tablename__ = "player_external_ids"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]
    external_id: Mapped[str]


class _StatColumns:
    """Season totals. Per-game = total / gp, computed when read."""

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]
    season: Mapped[str]  # "2026-27"
    gp: Mapped[float]
    fgm: Mapped[float]
    fga: Mapped[float]
    ftm: Mapped[float]
    fta: Mapped[float]
    tpm: Mapped[float]
    pts: Mapped[float]
    reb: Mapped[float]
    ast: Mapped[float]
    stl: Mapped[float]
    blk: Mapped[float]
    tov: Mapped[float]
    fetched_at: Mapped[datetime]


class PlayerProjection(_StatColumns, Base):
    __tablename__ = "player_projections"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)


class PlayerSeasonStats(_StatColumns, Base):
    """Actual season totals: past seasons and the current one, one row per season."""

    __tablename__ = "player_season_stats"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)


class PlayerMarketValue(Base):
    """Values a source publishes (Yahoo auction value, average cost, ADP).

    Values computed by our own models do not go here; they get their own table (T-010).
    """

    __tablename__ = "player_market_values"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]
    season: Mapped[str]
    auction_value: Mapped[float | None]
    average_cost: Mapped[float | None]
    average_pick: Mapped[float | None]
    percent_drafted: Mapped[float | None]
    rank: Mapped[int | None]
    positions: Mapped[list[str] | None] = mapped_column(JSON)  # eligible positions in this source
    injury: Mapped[str | None]
    injury_note: Mapped[str | None]
    extra: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime]


class NbaGame(Base):
    __tablename__ = "nba_schedule"
    __table_args__ = (UniqueConstraint("source", "source_game_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]  # "espn"
    source_game_id: Mapped[str]
    season: Mapped[str]
    start_utc: Mapped[datetime]
    game_date_et: Mapped[date] = mapped_column(index=True)
    home: Mapped[str]
    away: Mapped[str]
    neutral_site: Mapped[bool]
    fetched_at: Mapped[datetime]
