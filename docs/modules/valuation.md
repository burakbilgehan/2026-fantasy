# Valuation (T-017 research, T-010 engine, T-011 table)

Handoff from the refinement session of 2026-10-04. A new session can start T-017 / T-010 from this file.
This file replaces the "Valuation (M1)" section of `docs/modules/draft.md`. User decisions are marked (user). Everything else is a proposal until the user accepts it.

## What the user gets
A player value table. The user picks a base and a model; the table gives every player a value and a dollar price. The same engine feeds the draft board (T-018).

## Core rule (user)
A model is a function. Every model runs on every base. The user changes the base or the model in a dropdown and the numbers update at once.

Four independent pickers:
1. **Source**: real stats of a season (`player_season_stats`, source `nba`, 2023-24 to 2025-26), Yahoo projection (2026-27), ESPN projection (2026-27 and the 2025-26 preseason one), later our own projection (T-025), or an average of sources.
2. **Basis**: per game, totals (per game x GP or projected GP), later per 36 minutes.
3. **Model**: see the list below.
4. **Dollar conversion**: plain value over replacement, or SAVOR.

Extra inputs, not bases: G-score needs week-to-week variance (`player_game_logs`). H-score needs the draft state and my team. Market prices are data, not a function.

## Decisions (user, 2026-10-04)
- Keep all models. More models is better. Add our own models and keep looking for better ones. Later, move the most used models to the top of the list.
- Every model shows a short description next to the dropdown, so the user knows what he picks. The text below is the first draft of these descriptions.
- Every player gets a value, not only the drafted ones.
- Projected GP goes into the totals basis. Per game stays its own view.
- Position does not go into the value. It is a warning only.
- Success measure: weekly H2H simulation. Not a roto-style total.
- No paid sources.
- Stats views always show all 9 categories plus GP and minutes, also when a model ignores a category.

## Open
- Reference pool for the category average and standard deviation. Not the top 156, not a minutes cut alone (user): low-minute players who play every game and handcuffs (example: Paul Reed) are part of the real pool. Make the pool a setting and compare candidates in the backtest (for example: top N by the model's own value with N = 144, 200, 250; all players with a projection).
- Exact formulas for balance score, fluff indicator and reliability score.
- H-score: read the paper and the open source tool first (license not checked).

## Models (name, one-line description for the UI, status)
| Model | Description for the dropdown | Notes |
|---|---|---|
| Z-score 9-cat | Classic. Each category: distance from the pool average in standard deviations. Sum of 9. | FG% and FT% as volume-weighted impact. TO negative. Method of Basketball Monster and Hashtag. |
| Punt z-score | Classic, with the categories you turn off removed. | Category toggles. |
| Minus-1 | Classic, without each player's own worst category. | Basketball Monster definition (verified, their help text). Fixes stars with one terrible category (Antetokounmpo, Williamson). |
| DURANT approximation | Minus-1 without turnovers. Our guess at Josh Lloyd's H2H ranking. | The real formula is closed. Lloyd's rank quotes in `docs/knowledge/claims.md` can check how close we are. |
| G-score | Classic, but noisy categories (steals, percentages, turnovers) weigh less, because weekly results in them are closer to luck. | arXiv 2307.02188. Needs week-to-week variance from `player_game_logs`. Paper weights vs z-score: STL 44%, FG% 56%, FT% 58%, TO 62%, PTS 65%, BLK 68%, REB 69%, 3PM 72%, AST 75%. Compute our own from the logs. |
| H-score | Value of a player for my team right now. Changes after every pick. Finds punts by itself. | arXiv 2409.09884, tool: zer2.github.io/fantasy-basketball-optimizer. Needs draft state. Build after the static models. |
| Balance score | How evenly the value is spread over categories. Not a value; a second number. | Formula open. |
| Fluff indicator | Gap between 9-cat rank and fantasy-points rank. Large gap = the 9-cat rank flatters or hides the player. | Own idea, from Lloyd's "nine-cat fluff". Formula open. |
| Reliability score | Share of games played in the last 3 seasons. A second number. | Lloyd: GP cannot be predicted (r about 0.3), except repeated lower-body injuries. |
| Market | Not a model: Yahoo average cost, ESPN average auction price, our league's 2025-26 prices. | `player_market_values`, `draft_picks`. Signal = model dollars minus market dollars. |

Dollar conversion:
- **Plain**: value above replacement level, scaled so that all drafted players share 12 x 200 USD minus 1 USD per roster spot. 144 players are drafted (12 non-IL slots, read from league settings).
- **SAVOR**: same, but cheap players are worth less because they are replaced from waivers during the season, so stars get more. One parameter (spread, default 10 in the reference tool). Evidence in our league: 27 of 144 players went for 1 USD and 44 for 3 USD or less in 2025-26.

## Backtest plan (T-017, first run)
Data is ready: ESPN 2025-26 preseason projection (381 players), real 2025-26 totals (578), game logs for 3 seasons (73836 rows), our league's 144 prices of 2025-26.
1. Run every model on the 2025-26 preseason projection. Convert to dollars.
2. Run every model on the real 2025-26 season. Compare: which preseason model was closest to the end-of-season truth of the same model.
3. Compare model dollars with our league's real prices: where does this league overpay or underpay (stars, injured players, categories).
4. Weekly H2H simulation with the game logs: build teams by each model's dollars, play the 2025-26 weeks, count category wins against the other teams. This is the success measure.
5. Bring the result to the user as tables. The user decides what stays on top.

This backtest measures models and the league's pricing. It does not measure how good a projection source is; that belongs to T-025.

## Build notes for T-010
- Pure functions: `value(base_rows, model, settings) -> per-player category values, total, dollars`. No DB access inside the function.
- Unit tests per model with a small fixed pool.
- API: one endpoint with source, season, basis, model, punt list, dollar conversion and pool as parameters.
- Model descriptions live in one place (a registry) and the frontend reads them from the API.
