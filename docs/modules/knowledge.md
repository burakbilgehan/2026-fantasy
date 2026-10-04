# Expert knowledge synthesis (T-022, M8 second layer)

Handoff from the refinement session of 2026-10-04. A new session can start T-022 from this file.
User decisions are marked (user). Everything else is a proposal until the user accepts it.

## What the user gets
A living, LLM-written documentation on top of the raw expert notes: short profiles for players and teams, tags, and articles. It updates when new videos or NBA news arrive, and drops what is outdated.

## Input (ready)
- Layer 1, T-021: `docs/knowledge/` (generated, do not edit). 96 of 96 Locked On videos from 2026-06-22 to 2026-10-04. Per-video JSON in `docs/knowledge/_data/videos/`, pages per player (424), team (30), `methods.md` (general rules), `claims.md` (factual claims).
- Raw transcripts: `data/raw/experts/youtube/{video_id}.json`. Use them to expand short or unclear notes around their timestamp.
- Our DB: stats of 3 seasons, game logs, projections (Yahoo, ESPN), market prices, our league's 2025-26 auction.
- New videos: `make expert-run`. When the caption endpoint is blocked, use the Chrome transcript panel (see T-021 in `TASKS.md`).

## Layers (user)
1. Raw notes. Unchanged.
2. Profiles: one per player, one per team. Same structure for both.
3. Articles and compilations. Not only about players and teams (see below).

## Profile rules (user)
- Two channels: **durable** (skills, category profile, injury history) and **current** (role, form, health, price, expert calls).
- Two kinds of statement: **fact** and **verdict**. A fact stays until a newer fact replaces it. For verdicts the newest wins and the older one is dropped.
- No history. The profile states the latest situation only (Nesmith: he is a bounce-back candidate now; do not write that he was bad before).
- A short-term call does not define the player. "Drop" after two bad months stays in the current channel and does not hide what he can be for the rest of the season.
- No default time limit on current statements. A statement gets an end only when the source gives one: a date ("good schedule for the next 3 weeks") or an event ("until player X returns").
- Sources: the notes plus our own numbers. Not the LLM's own memory of the NBA: it is out of date.
- Stats in a table. Always all 9 categories plus GP and minutes. Three seasons and the projections. Prices in a second table.
- Each profile ends with a note of 2 to 3 sentences: what this means for our league (prices, builds, what to check).
- Accepted trial format: `docs/knowledge/_demo/profiles-demo.md` (5 players, written by hand). Delete it when the pipeline output replaces it.

## Tags (user)
- Structured data, not words inside a paragraph: player or team, tag name, channel (durable or current), date, source note, optional end condition.
- Open list. No limit per player: 1 tag or 30, as needed.
- A tag must be useful as a filter or a search. Bad example: "two-category player".
- Every tag name has one meaning in `docs/GLOSSARY.md`. Add the term there when a new tag appears.
- Kinds seen so far: category role (AST specialist, REB specialist, FG% anchor, 3PM source), build fit (punt FT fit, punt AST fit, Giannis build fit), outlook (breakout, bust, bounce-back, flyer), risk (injury prone, load management, trade risk, shutdown risk, back-to-back risk), durability in the good direction (plays every game), market (expert target, bust candidate at a site's price, sites disagree on price), expert calls in season (must add, drop, sell high, buy low), schedule (good or bad playoff schedule), handcuff.
- Tags feed: compilations, the draft panel (T-018), and a tag filter on the player table (example in season: all "buy low" players).

## Articles and compilations (user)
- First list: one sheet per punt build (FT%, AST, TO and others) with the players who fit; breakout candidates; bust candidates; late-round flyers; injury, shutdown and trade risk; auction tactics; strategy by draft stage.
- Topics that are not about one player or team also get articles. User examples: do not draft by predicted injuries (except chronic cases such as Embiid's knee); fantasy playoff weeks matter; teams with 2 games or 5 games in a week are outliers and need weekly adjustments. `methods.md` is the main input for these.
- The list is open on purpose. While reading, the LLM proposes new articles from patterns it finds, also ones nobody asked for. After the first synthesis, run one more pass that looks for new links across profiles, tags and articles.
- Players in a compilation show their T-017 values when the engine exists. Profiles and tags do not wait for T-017.

## Updating (user)
- New video or NBA news: re-run only the profiles, tags and articles it touches. Outdated statements are removed, not kept as history.
- Increments are small (user, 2026-10-04): a new video touches only the players and teams in its notes. Per profile the job is a merge and a contradiction check: add new facts, drop replaced verdicts, fix tags. Not a rebuild.
- Numbers are written by code, not by the LLM. The stat table refreshes on every data sync. Code watches thresholds (example: minutes up by 5 in two weeks, FG% far from the season average) and marks the profile dirty; only then the LLM rewrites text and tags. Tags such as "sell high" and "buy low" can also come from the numbers. Thresholds: open, product decision.
- Drift guard (proposal): after 5 incremental updates, rebuild that one profile from the raw notes.
- Trigger (user, 2026-10-04): by command, not automatic. Fetching new videos can be automated (`make expert-run`).
- Change list (user, 2026-10-04): a separate "what changed" list is wanted if it is useful (example line: "Nesmith: new verdict, rank 110 to 130"). The profile itself keeps no history.
- The LLM for the synthesis can run at the highest setting. All LLM work goes through `claude -p` (see `CLAUDE.md`), prompts in `prompts/`, one folder per job.

## Open
- Storage: generated markdown as in layer 1, DB tables for tags, or both. Tags need a queryable store for the filter and the draft panel.
- How the LLM gets our numbers: a prepared stat block per player in the prompt (proposal).
- Order of the first run: profiles for the players who can be drafted (about 250), then teams, then articles (proposal).
- NBA news source for in-season updates. Not chosen.
- Check of LLM output: layer 1 has a quote check. Layer 2 needs its own check that every statement points to a note or a number (proposal).

## First steps for the session that takes T-022
1. Read this file, `docs/GLOSSARY.md`, the demo, and `prompts/expert_digest/` plus `backend/app/experts/` for the layer 1 pattern.
2. Propose the storage and the prompt. Show the user the plan before the build (product work).
3. Run 5 to 10 players through the pipeline and compare with the hand-written demo.
4. Then all players, teams, and the first articles.
