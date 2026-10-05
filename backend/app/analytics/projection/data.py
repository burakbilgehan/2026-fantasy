"""DB loading for the projection engine (T-025). The engine and fit stay pure; this module reads.

Past minutes: `player_season_stats.min` is empty for source nba, so minutes per season are the
sum of the regular season game logs (`player_game_logs`).
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import func, inspect, select, text

from app.analytics.projection.engine import Season
from app.models import Player, PlayerGameLog, PlayerSeasonStats

FIELDS = ("fgm", "fga", "ftm", "fta", "tpm", "reb", "ast", "stl", "blk", "tov")


def season_age(birth: date | None, season: str) -> int | None:
    """Age on 1 February of the season (the middle of the season)."""
    if birth is None:
        return None
    mid = date(int(season[:4]) + 1, 2, 1)
    return mid.year - birth.year - ((mid.month, mid.day) < (birth.month, birth.day))


def birth_dates(db) -> dict[int, date]:
    cols = {c["name"] for c in inspect(db.get_bind()).get_columns("players")}
    if "birth_date" not in cols:
        return {}
    out = {}
    for pk, b in db.execute(text("select id, birth_date from players where birth_date is not null")):
        out[pk] = b if isinstance(b, date) else date.fromisoformat(str(b)[:10])
    return out


def load_history(db) -> tuple[dict[int, dict[str, Season]], dict[int, str | None], dict[int, date]]:
    """({player: {season: Season}}, {player: position}, {player: birth date}).
    Seasons without game logs (no minutes) are left out."""
    minutes = defaultdict(float)
    for pk, season, m in db.execute(
        select(PlayerGameLog.player_pk, PlayerGameLog.season, func.sum(PlayerGameLog.min))
        .where(PlayerGameLog.season_type == "regular")
        .group_by(PlayerGameLog.player_pk, PlayerGameLog.season)
    ):
        minutes[(pk, season)] = m
    births = birth_dates(db)
    data: dict[int, dict[str, Season]] = defaultdict(dict)
    for r in db.scalars(select(PlayerSeasonStats).where(PlayerSeasonStats.source == "nba")):
        m = minutes.get((r.player_pk, r.season))
        if m is None:
            continue
        data[r.player_pk][r.season] = Season(
            season=r.season, gp=r.gp, min=m, stats={f: getattr(r, f) for f in FIELDS},
            age=season_age(births.get(r.player_pk), r.season),
        )
    positions = {pk: normalise_position(pos) for pk, pos in db.execute(select(Player.id, Player.position))}
    return dict(data), positions, births


def normalise_position(pos: str | None) -> str | None:
    """'G-F' -> 'G,F'; 'PG' -> 'G' (league mapping in RULES.md)."""
    if not pos:
        return None
    m = {"PG": "G", "SG": "G", "SF": "F", "PF": "F"}
    parts = []
    for p in pos.replace("-", ",").split(","):
        p = m.get(p.strip(), p.strip())
        if p in ("G", "F", "C") and p not in parts:
            parts.append(p)
    return ",".join(parts) or None
