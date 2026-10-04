"""NBA season labels like "2026-27"."""

import os

import app.config  # noqa: F401  (loads .env before CURRENT_SEASON is read)

# Assumed default: the season this tool is built for. Override with CURRENT_SEASON.
CURRENT_SEASON = os.environ.get("CURRENT_SEASON", "2026-27")


def start_year(season: str) -> int:
    return int(season[:4])


def end_year(season: str) -> int:
    """2026-27 -> 2027. ESPN names a season by this year."""
    return start_year(season) + 1


def label(start: int) -> str:
    return f"{start}-{(start + 1) % 100:02d}"


def previous(season: str) -> str:
    return label(start_year(season) - 1)
