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
    min: Mapped[float | None]  # total minutes; None when the source has none
    fetched_at: Mapped[datetime]


class PlayerProjection(_StatColumns, Base):
    __tablename__ = "player_projections"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)


class PlayerSeasonStats(_StatColumns, Base):
    """Actual season totals: past seasons and the current one, one row per season."""

    __tablename__ = "player_season_stats"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)


class PlayerAdvancedStats(Base):
    """Advanced season stats (usage rate and others) per player, past seasons. Regular season only.

    Linked by the NBA person id only. Fractions as the source gives them (usg_pct 0.289 = 28.9%).
    The other advanced columns of the source go into `extra`.
    """

    __tablename__ = "player_advanced_stats"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]  # "nba"
    season: Mapped[str]
    gp: Mapped[float]
    usg_pct: Mapped[float | None]
    ts_pct: Mapped[float | None]
    extra: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime]


class PlayerGameLog(Base):
    """One row per player per game played. DNP games have no row.

    `season_type` keeps preseason games apart: season totals are regular season only.
    """

    __tablename__ = "player_game_logs"
    __table_args__ = (UniqueConstraint("player_pk", "source", "game_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]  # "nba"
    season: Mapped[str]  # "2025-26"
    season_type: Mapped[str] = mapped_column(server_default="regular")  # "regular" or "preseason"
    game_id: Mapped[str]  # source game id
    game_date: Mapped[date] = mapped_column(index=True)  # US Eastern date, as the source gives it
    team: Mapped[str | None]  # canonical abbreviation at that game
    opponent: Mapped[str | None]
    home: Mapped[bool]
    min: Mapped[float]
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


class PlayerMinutesProjection(Base):
    """Projected minutes per game from sources that have no full stat line (T-026).

    DARKO has no games played; FantasyPros has no shot attempts. ESPN minutes stay
    in player_projections.min. Everything else the source gives goes into `extra`.
    """

    __tablename__ = "player_minutes_projections"
    __table_args__ = (UniqueConstraint("player_pk", "source", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_pk: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str]  # "darko", "fantasypros"
    season: Mapped[str]
    team: Mapped[str | None]  # team the source gives, canonical abbreviation
    mpg: Mapped[float]  # minutes per game played
    gp: Mapped[float | None]  # projected games played; None when the source has none
    extra: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime]


class DepthChartEntry(Base):
    """One player in one position slot of a team depth chart. A sync replaces the source's rows.

    `depth` is the source's tier (1 = starter). Several players can share a tier;
    `order` is the position in the source's list.
    """

    __tablename__ = "depth_charts"
    __table_args__ = (UniqueConstraint("source", "season", "team", "slot", "order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]  # "hashtag"
    season: Mapped[str]
    team: Mapped[str]  # canonical abbreviation
    slot: Mapped[str]  # PG, SG, SF, PF, C
    depth: Mapped[int]
    order: Mapped[int]
    player_pk: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    player_name: Mapped[str]  # as the source writes it
    fetched_at: Mapped[datetime]


class TeamWinTotal(Base):
    """Season win total lines (over/under) per NBA team."""

    __tablename__ = "team_win_totals"
    __table_args__ = (UniqueConstraint("source", "season", "team"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]  # "sportsbettingdime"
    season: Mapped[str]
    team: Mapped[str]
    wins: Mapped[float]
    over_odds: Mapped[int | None]  # American odds, like -110
    under_odds: Mapped[int | None]
    fetched_at: Mapped[datetime]


class SyncRun(Base):
    """One run of a refresh job (app/jobs/refresh.py). Read by GET /api/sync/status."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(index=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    ok: Mapped[bool | None]  # None while running
    message: Mapped[str | None]


class KnowledgeTag(Base):
    """One tag on a player or team profile (T-022). Rebuilt from the profile JSON on every render.

    `tag` is the canonical name from docs/knowledge/_data/tags.json; `raw_name` is what the
    LLM wrote. Tags removed by the category check are not stored.
    """

    __tablename__ = "knowledge_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str]  # "player" or "team"
    player_pk: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    team: Mapped[str | None] = mapped_column(index=True)  # team code for team profiles
    tag: Mapped[str] = mapped_column(index=True)
    raw_name: Mapped[str]
    kind: Mapped[str | None]
    channel: Mapped[str]  # "durable" or "current"
    detail: Mapped[str | None]
    until: Mapped[str | None]
    sources: Mapped[list[str]] = mapped_column(JSON)
    classified: Mapped[bool]  # False = name not in the registry yet
    built_at: Mapped[datetime]
