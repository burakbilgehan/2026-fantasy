# Projection context layer prompts (T-025)

One call per NBA team. Code: `backend/app/analytics/projection/context.py`. Run: `make projection ARGS="context CHA BKN OKC"`, then `make projection ARGS=run`.

Input: the team profile, every player on the team with our base projection (code), ESPN and Yahoo projections, past seasons, depth chart, and the player profile (expert notes).
Output: per player, adjustments on top of the base layer (minutes, games out at the start, late-season games out, category multipliers), a floor and a ceiling scenario, and a reason for each change. The engine turns them into stat lines, so PTS stays 2 FGM + FTM + 3PM.
Stored in `projection_adjustments` with source `llm`. A manual row (source `manual`) wins field by field.

## Where files live (one rule)
- `prompts/projection_team/`: the source. Edit prompts only here. In git.
- `data/projection_context/`: generated, not in git, never edit by hand. Can be deleted and rebuilt.
  - `{TEAM}.json`: the full LLM answer per team (the same values are in the DB table `projection_adjustments`).
  - `inputs/league_players.csv`: the league table the LLM can read. Rewritten on every run.
  - `preview/`: the exact prompts as sent (`make projection-prompt TEAM=CHA`). For reading only.
  - `review/{TEAM}.md`: base vs adjusted lines with the reasons (`make projection-review TEAM=CHA`).
- `data/projection_params.json`: fitted base parameters (`make projection ARGS=fit`).
