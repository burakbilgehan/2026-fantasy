"""Canonical NBA team abbreviations.

Canonical = NBA.com abbreviations. Yahoo uses the same 30 (verified 2026-10-04,
player feed vs nba.com/players). ESPN differs for six teams.
"""

NBA_TEAMS = frozenset({
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
})

ALIASES = {
    "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
    "PHO": "PHX",  # Hashtag Basketball, FantasyPros
    "NOR": "NOP", "UTH": "UTA",  # FantasyPros
}

# Full names (DARKO, Vegas win totals pages). Verified 2026-10-04: the same 30 names on both.
FULL_NAMES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def canonical(abbr: str | None) -> str | None:
    """Canonical abbreviation, or None for a free agent / unknown team."""
    if not abbr:
        return None
    abbr = ALIASES.get(abbr.upper(), abbr.upper())
    return abbr if abbr in NBA_TEAMS else None


def from_full_name(name: str | None) -> str | None:
    """Full team name to abbreviation (Denver Nuggets -> DEN). None when unknown."""
    return FULL_NAMES.get((name or "").strip())
