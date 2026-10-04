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
}


def canonical(abbr: str | None) -> str | None:
    """Canonical abbreviation, or None for a free agent / unknown team."""
    if not abbr:
        return None
    abbr = ALIASES.get(abbr.upper(), abbr.upper())
    return abbr if abbr in NBA_TEAMS else None
