"""Player data sources. Add a source: see docs/ARCHITECTURE.md, "Player data sources".

Order matters: `sync_players` runs sources in this order when none is given,
and earlier sources win when two disagree on a player's team or position.
"""

from app.sources.players.base import PlayerSource
from app.sources.players.nba_index import NbaIndex
from app.sources.players.yahoo_pubapi import YahooPlayers

SOURCES: dict[str, PlayerSource] = {s.key: s for s in (NbaIndex(), YahooPlayers())}
