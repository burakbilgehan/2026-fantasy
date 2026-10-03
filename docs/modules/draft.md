# M1 + M2: Player value table and live auction draft board

## User workflow on draft day
1. The user opens two tabs: the Yahoo draft room and our Draft page.
2. The user does all nominations and bids on Yahoo.
3. Our page gets draft events from the extension (or the API poller when approved) and updates.
4. When a player is nominated on Yahoo, the user finds him in our table and reads the price range.

## Display rule: per-game first (user decision, 2026-10-03)
- Default stat view = per-game values computed from projected season totals (total / projected GP). Example: 300 3PTM in 80 games is shown as 3.75.
- Always show projected GP next to per-game values. Durability matters: equal totals over 60 vs 80 games mean different players.
- Season totals stay available (column toggle or tooltip). Both are needed, but per-game is the main reading view.
- Team views: mean per-game value of the team's drafted players for counting stats. FG% and FT%: total makes / total attempts (volume-weighted).
- Team ranking default: simulated H2H, 9 categories, each team vs every other team. Teams with no players are listed, not skipped.

## Valuation (M1)
1. Get per-game projections for all players. Multiply by projected games.
2. Compute a z-score per category. FG% and FT%: use volume-weighted impact (makes minus league-average makes at the player's attempts). TO: negative.
3. Total value = sum of category z-scores. The user can turn off categories (punt). Values then recompute.
4. Replacement level: the player at rank (12 teams x roster size). Roster size comes from Yahoo league settings.
5. Dollar value: value above replacement, scaled so all drafted players share (12 x $200) minus ($1 x roster spots). Each drafted player gets at least $1.

## Dynamic price range (M2)
- Base price: dollar value from M1.
- Market price: last season's auction price of the player at the same rank (from Yahoo history). Shows how this league pays.
- Inflation: (money left in the league minus $1 per open roster spot) / (dollar value left in undrafted top players). Above 1.0 means players will go higher than base.
- Shown range per player: low = min(base, market) x inflation, high = max(base, market) x inflation. The exact formula is decided and tested in P1.
- Per team: money left, open spots, max bid (money left minus $1 per other open spot).

## Team profiles (M2)
- For each team: category totals of drafted players, as z-score sums and as rank in the league (1 to 12).
- My team: strengths, weaknesses, detected punt (for example "FT% very low: punt FT% fits").
- Hints: players who fit my build. Example: after Giannis, rank players with FT% turned off.
- Hints are rules and numbers, not LLM text.

## Manager tendencies (M4 part, if time in P1)
- From last season's auction: how much each manager spent on the top 10, top 30, and $1 players.
- Shown as a small note per team on the board.

## Draft data source
- No manual entry mode (user decision, 2026-10-03).
- Primary until Yahoo approves the API: local Chrome extension in the user's draft tab (T-009). It reads the draft room WebSocket (verified on mock 2600009, 2026-10-03).
- WebSocket messages (meaning inferred from the mock, consistent with all data seen): `D|pick|team|sec` nomination turn, `n|team|player|bid|sec` nomination, `b|team|player|bid|sec` bid, `0|pick|player|team|slot|price` sale, `$|team=money...` budgets, `P|pick=player,team,price|...` all past picks (sent on every connect, so a page reload recovers full state, verified).
- The draft client also loads `pub-api.fantasysports.yahoo.com/fantasy/v3/{players,teams,settings,draftstatus}/nba/{league}`. `players` has 707 players with Yahoo projected stats, last season stats, auction value, average cost (verified).

## Open questions
- Roster size and positions: read from Yahoo settings in P0.
- Projection source: decide in P0 after `DATA_SOURCES.md` checks.
