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

## Decisions (user, 2026-10-13), from `valuation-models-research.md`
- Default model: G-score (was Minus-1). It tracks the empirical weekly H2H value best (Spearman 0.98 over 4 seasons) and wins the hindsight draft tournament every season.
- DURANT: the approximation is replaced by Josh Lloyd's published formulas (joshlloydfantasy.com/research/durant-fantasy-basketball, read 2026-10-13): Yeo-Johnson transform per category, then z; DURANT H2H = weights PTS 1.00, REB 0.94, AST 0.75, the rest 0.60, no turnovers, Minus 1; broad DURANT = all 1.00, turnovers 0.50. Per game, pool all, as he uses them. Reproduces 41 of his quoted 2025-26 ranks at Spearman 0.99.
- New own model "Simulated H2H" (`simulate.py`): expected weekly lines (per game x the team's games that week x availability) for hundreds of random teams drawn from the top 144, all-play per fantasy week. Value = category wins above 50% per 100 matchups. Runs on any base: the NBA schedule for the current season, the game logs for past seasons. About 1.5 s, cached per base.
- Format gap built as two table columns: FPts (Yahoo points-league formula per game) and Cat vs Pts = points-league rank minus the model's rank; green = worth more in categories than in points (the room underpays), red = the reverse (user reading, 2026-10-13). See GLOSSARY "Cat vs Pts".
- Not added: Minus-2, percentile z, robust z (research candidates, weak in the tests); percentage volume scaling (no evidence: Spearman change under 0.001).
- G-score kappa now uses the roster size (12), as in the paper; weights moved by about 1%.

## Open
- Reference pool: decided 2026-10-04 (user): default top 200 by the model's own value. Stays a setting. Backtest: 144, 200, 250 and all are within noise.
- Default model: decided 2026-10-04 (user): Minus-1; changed 2026-10-13 (user): G-score. The value table and the draft board start with it. All models stay in the dropdown.
- (Old note) Reference pool for the category average and standard deviation. Not the top 156, not a minutes cut alone (user): low-minute players who play every game and handcuffs (example: Paul Reed) are part of the real pool. Make the pool a setting and compare candidates in the backtest (for example: top N by the model's own value with N = 144, 200, 250; all players with a projection).
- Exact formulas for balance score, fluff indicator and reliability score.
- H-score: read the paper and the open source tool first (license not checked).

## Models (name, one-line description for the UI, status)
| Model | Description for the dropdown | Notes |
|---|---|---|
| Z-score 9-cat | Classic. Each category: distance from the pool average in standard deviations. Sum of 9. | FG% and FT% as volume-weighted impact. TO negative. Method of Basketball Monster and Hashtag. |
| Punt z-score | Classic, with the categories you turn off removed. | Category toggles. |
| Minus-1 | Classic, without each player's own worst category. The value for a team that punts that category. | Basketball Monster definition (verified, their help text). Fixes stars with one terrible category (Antetokounmpo, Williamson). Research 2026-10-13: a punt-optimistic view; weaker than G-score for an average team. |
| DURANT H2H (Lloyd) | Josh Lloyd's head-to-head list as he published it: skew-corrected categories (Yeo-Johnson), points weigh most, no turnovers, the player's worst category dropped. Per game, pool all. | Published formula (verified 2026-10-13). Replaced the "DURANT approximation" (Minus-1 without TO). |
| DURANT (Lloyd, all categories) | Lloyd's broad DURANT for roto and H2H: skew-corrected categories, all equal, turnovers at half weight. | Same source. |
| Simulated H2H | Our own model: the player joins hundreds of random teams that play every fantasy week on expected weekly lines; value = category wins above 50% per 100 matchups. | `simulate.py`, numpy. Research note 2026-10-13. Deterministic lines (no week-to-week noise yet). The team-conditional version for the draft assistant is the next step. |
| G-score | Classic, but noisy categories (steals, percentages, turnovers) weigh less, because weekly results in them are closer to luck. Default since 2026-10-13. | arXiv 2307.02188. Needs week-to-week variance from `player_game_logs`. Paper weights vs z-score: STL 44%, FG% 56%, FT% 58%, TO 62%, PTS 65%, BLK 68%, REB 69%, 3PM 72%, AST 75%. Compute our own from the logs. |
| H-score | Value of a player for my team right now. Changes after every pick. Finds punts by itself. | arXiv 2409.09884, tool: zer2.github.io/fantasy-basketball-optimizer. Needs draft state. Build after the static models. |
| Balance score | How evenly the value is spread over categories. Not a value; a second number. | Formula open. |
| Cat vs Pts (fluff indicator) | Gap between the model's rank and the points-league rank. Green = category value above points value. | Built 2026-10-13 as table columns FPts and Cat vs Pts (points-league rank minus model rank; Yahoo formula PTS + 1.2 REB + 1.5 AST + 3 STL + 3 BLK - TO). |
| Reliability score | Share of games played in the last 3 seasons. A second number. | Lloyd: GP cannot be predicted (r about 0.3), except repeated lower-body injuries. |
| Market | Not a model: Yahoo average cost, ESPN average auction price, our league's 2025-26 prices. | `player_market_values`, `draft_picks`. Signal = model dollars minus market dollars. |

Dollar conversion:
- **Plain**: value above replacement level, scaled so that all drafted players share 12 x 200 USD minus 1 USD per roster spot. 144 players are drafted (12 non-IL slots, read from league settings).
- **SAVOR**: same, but cheap players are worth less because they are replaced from waivers during the season, so stars get more. One parameter (spread, default 10 in the reference tool). Evidence in our league: 27 of 144 players went for 1 USD and 44 for 3 USD or less in 2025-26.

## Backtest plan (T-017, first run)
Status: first run done 2026-10-04. Results: `valuation-backtest.md`. Code: `backend/app/analytics/valuation/` (models), `backend/app/analytics/h2h_backtest.py`, `backend/app/jobs/valuation_backtest.py`.

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
