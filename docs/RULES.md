# League rules

Rules of our Yahoo league and general fantasy basketball facts. Loaded into every session via `CLAUDE.md`.
Status words: `verified` (checked on Yahoo or with the user), `inferred`, `assumed`.

## League (Yahoo NBA, league 23772, "Deh Deh")
Source: public settings page https://basketball.fantasysports.yahoo.com/nba/23772/settings , synced 2026-10-03 (verified), and the user (2026-10-03).
- 12 teams. Head-to-head, categories. Not a cash league.
- League renewed every season (about 7 seasons). 2025-26 was auction (verified: league 38073 settings, "Live Salary Cap Draft", $200, bid time 10 s). Older seasons were snake.
- Team ids and team names in 2025-26 (league 38073) are the same as in 2026-27 (verified 2026-10-04). Same manager per team id: inferred.
- Managers are experienced. Trades are very frequent. Trade tools have high value.

### Categories (9-cat)
- FG%, FT%, 3PTM, PTS, REB, AST, ST, BLK, TO.
- TO: lower is better.
- FG% and FT% are ratios. A team's value = total makes / total attempts, so high-volume players move them more.

### Roster
- Slots: G, G, G, F, F, F, C, Util, Util, Util, BN, BN, IL, IL, IL, IL.
- 10 starters, 2 bench, 4 injured list. 16 slots in total, 12 without IL.
- Lineups change daily ("Weekly Deadline: Daily - Today", inferred).
- Injured players from waivers or free agency can go directly into IL (verified).

### Positions
- Yahoo gives eligibility in the league's own set: G, F, C (verified, league player feed, 2026-10-04).
- Mapping from other sources (user, 2026-10-04): PG and SG = G. SF and PF = F. C = C.
- Util takes any player. A player can be eligible for more than one position (example: G,F).

### Draft
- Live auction (Yahoo "Live Salary Cap Draft"). Sunday 2026-10-18, 3:00pm EDT.
- Budget $200 per team. No keepers. Draft pick trades not allowed.
- Nomination time 30 s, bid time 20 s.
- Players not drafted follow waiver rules after the draft.
- The draft fills only the non-IL slots (user, 2026-10-04). Now 12 per team (10 starters + 2 BN), so 144 players in the league draft. If the league changes BN count, this number changes: read it from the roster slots.
- IL slots fill during the season: put an injured player on IL, then add a player to the open slot.

### Season and transactions
- Scoring starts week 1.
- Waivers: FAB (free agent budget) with continual rolling list tiebreak. Waiver time 1 day. Processed every day.
- Max 6 acquisitions per week. No season maximum.
- Trades: no maximum, no review. Trade deadline 2027-03-04.
- Playoffs: 8 teams, weeks 19, 20, 21, ends Sunday 2027-03-28. Higher seed wins ties. No reseeding.
- Can't-cut list: Yahoo Sports.

## General fantasy basketball facts
- H2H categories: each week, you win or lose each category against one opponent. A 9-cat week ends like 5-4-0.
- Punting: give up one or more categories on purpose to be stronger in the others (common punts: FT%, TO, FG%, AST).
- Games played matter: a player's weekly counting stats depend on how many games the player's team plays that week (`nba_schedule`).
