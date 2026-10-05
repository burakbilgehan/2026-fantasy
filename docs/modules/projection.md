# Own projection (T-025)

Our own 2026-27 projection for every player: a median line, a floor and a ceiling. It feeds the value table (source `own` in the source picker) and later the draft board and the player drawer.
A new session can continue T-025 from this file.

## Data flow diagram
`docs/modules/projection-flow.html` (`make flow`, template `backend/app/analytics/projection/flow_template.html`), published at https://claude.ai/artifact/Rw4PjAqVkZjrtv3WnNFerU with the age of every source. Keep it current when sources or steps change.

## Layers
1. **Base v2 (code, no LLM): weighted consensus** (user, 2026-10-05). Code `backend/app/analytics/projection/consensus.py`.
   - Per game, each component averaged over the sources that have it: Yahoo 2, FanScout 1, Fantrax 1, ESPN 1, FantasyPros 1 (no attempts), own stat model 1 (Fantrax lowered from 2 on 2026-10-05, see DATA_SOURCES.md). Turned into per-minute rates at the consensus minutes, so PTS = 2 FGM + FTM + 3PM.
   - Minutes: FanScout, Fantrax, ESPN, FantasyPros, equal weights (Yahoo publishes no minutes, verified: 0 of 506 rows); else last season; else DARKO.
   - Games: Yahoo's projected GP, else ESPN x 0.917, else our GP model (median season).
   - Own stat model (source `own-stat`): last 3 seasons weighted 6/3/1, pulled toward the position average by K per stat (fitted), age curve (fitted), at the consensus minutes.
   - Output: `player_projections` sources `own-base` (consensus) and `own-stat`.
2. **Context layer (LLM, `claude -p`, one call per team).** Judges the consensus in absolute terms (close to it when it is right, far from it with a reason; never mechanical). Reads the team and player profiles, the articles and the extra numbers, and returns per player: usage (USG%), minutes, games, games out, late games out, rate multipliers, floor and ceiling (per game only), reasons and a summary. Stored in `projection_adjustments` source `llm`.
3. **Manual corrections.** Same table, source `manual`. Wins over `llm` field by field. No form yet (see Open).
4. **Apply.** `run` combines 1 to 3 into `own`, `own-floor`, `own-ceiling`.

## Where the model lives (change the model without touching the plumbing)
| What you want to change | Where |
|---|---|
| How the LLM thinks: rules, league background, goals, examples | `prompts/projection_team/system.md` |
| What the LLM gets per team (tables, splits, profiles) | `prompts/projection_team/user_prompt.md` and `backend/app/analytics/projection/context.py`, `context_data.py` |
| What the LLM returns (fields) | `prompts/projection_team/schema.json` (then the storage in `context.py`) |
| LLM model and effort | `prompts/projection_team/config.json`. Raise `prompt_version` on every prompt change. |
| Base: season weights, K, GP, age | refit with `make projection ARGS=fit` (`data/projection_params.json`); method in `backend/app/analytics/projection/fit.py`, `engine.py` |
| Minutes and GP source order | `minutes_chain` and `cmd_run` in `backend/app/jobs/projection.py` |

Every `llm` row stores `model` = prompt version and hash, so a result can be traced to the prompt that made it.
After a model change: run the context layer again for the teams you want, then check the review files.

## Commands
| Command | What it does |
|---|---|
| `make projection ARGS=fit` | Fit the base parameters on past seasons. |
| `make projection ARGS=backtest` | Base vs ESPN on 2025-26. Writes `projection-backtest.md`. |
| `make projection ARGS=run` | Rebuild base and apply all adjustments. Free, seconds. |
| `make projection-context TEAMS="CHA BKN OKC"` | Context layer for these teams (empty = all 30), then `run`. About 0.80 USD list and 2 to 3 minutes per team (pilot, prompt v1). |
| `make projection-review TEAM=CHA` | Base vs adjusted with reasons; also writes `data/projection_context/review/CHA.md`. |
| `make projection-prompt TEAM=CHA` | Write the exact prompts to `data/projection_context/preview/` without an LLM call. |

## Data
- DB: `player_projections` (sources `own-base`, `own`, `own-floor`, `own-ceiling`; `extra` holds where minutes, games and rates came from), `projection_adjustments` (llm and manual inputs, reasons, summary, usage, model).
- Files, not in git, never edited by hand: `data/projection_context/` (`{TEAM}.json` raw LLM answer, `review/`, `preview/`, `inputs/league_players.csv`), `data/projection_params.json`.
- The LLM can read `docs/knowledge/` and `data/projection_context/inputs/` with read-only tools; nothing else (verified 2026-10-05).

## Decisions (user, 2026-10-05)
- Base = weighted consensus (Yahoo 2, FanScout 1, Fantrax 1, ESPN 1, FantasyPros 1, own stat model 1; Fantrax lowered from 2 after the check). Minutes: Fantrax, ESPN, FantasyPros; DARKO not trusted. Games from Yahoo; the LLM lowers them for injury-prone players.
- The LLM's numbers are absolute judgments, not mechanical edits.
- Fantrax is one of the three big sources: shown on the site next to Yahoo and ESPN (Fantrax ADP; Fantrax has no auction prices).
- No pull toward consensus; the user flags odd values.
- Floor and ceiling are about performance per game, not games played.
- Volume and usage matter as much as percentages: show FGA and FTA next to FG% and FT%, and project usage.
- Second-year players: natural development on top of role changes.
- Shutdown and late rest in v1, from the notes first, Vegas as one input.
- One LLM call per team. Prompts long and rich (it is a key decision tool).
- Results go to the DB; markdown is only the pilot review view.

## Backtest (base only)
`docs/modules/projection-backtest.md`. With ESPN's 2025-26 preseason minutes, the base equals ESPN on per game errors and ranks the real top 150 slightly better (0.766 vs 0.755). The context layer cannot be backtested (the model knows how 2025-26 went); its test is the season itself.

## Open
1. Pilot: run CHA, BKN, OKC with prompt v2, review, then all 30 teams (about 24 USD list).
2. Manual correction form in the player drawer (first write endpoint of the site).
3. Player drawer section: own vs ESPN vs Yahoo, floor and ceiling, usage, reasons.
4. Daily refresh: `run` every day (free). Context layer only for teams whose input changed (input hash), to keep cost low.
5. In-season check: own vs ESPN vs Yahoo against actual stats, weekly from November.
6. Known small bias: the age factor is one year of change applied to a multi-season average.
