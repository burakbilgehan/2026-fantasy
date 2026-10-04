# Vision and scope

One local site. It is the user's analysis desk for the whole season. It reads data, computes, and shows. It never acts on Yahoo.

All features are widgets. A widget reads from the backend API. Widgets share one data layer (players, stats, projections, league, teams, schedule).

## Modules

Status: `planned`, `in progress`, `done`. Phase refers to `ROADMAP.md`.

| # | Module | Purpose | Phase |
|---|--------|---------|-------|
| M0 | Core platform | Backend, DB, frontend shell, widget layout, Yahoo read sync, NBA data sync | P0 |
| M1 | Player value table | Customizable table. Per-category z-scores, total value, $ value, color scale. Filters, column choice, punt toggles. | P1 |
| M2 | Live auction draft board | Poll Yahoo picks. Dynamic price ranges with inflation. My team and all teams' category profiles. Punt detection and hints. | P1 |
| M3 | League dashboard | Category strength of every team. Simulated H2H matrix (each team vs each team). Standings context. | P3 |
| M4 | Manager profiles | League history: auction spending style, draft habits, waiver activity, trade activity and trade partners per manager. | P3 (draft-relevant part in P1 if time) |
| M5 | Trade analyzer | Evaluate a proposed trade for both sides by category impact and matchup impact. Search for good trade targets. Uses manager profiles. | P4 |
| M6 | Free agent scout | Rank available players by fit to my team, form, minutes, injury news, schedule. | P4 |
| M7 | Schedule and streaming planner | Games per team per week. Fantasy week planning. Weeks with few or many games. Streaming slots. | P4 |
| M8 | Expert digest | Ingest Josh Lloyd (Locked On Fantasy Basketball) and other sources. YouTube transcripts. LLM summary: trends, breakouts, waiver picks, schedule tips. | P5. First part (playlist to markdown knowledge base) done early in T-021 as input for T-017. |
| M9 | Season strategy | Weekly matchup outlook. Category targets for the week. Long-term punt and build advice. | P5 |

## Open product topics
Product topics need research and a refinement session with the user before any code. Items under "user examples" are examples from conversation, not the scope.

### Player valuation (big research topic)
- What makes a player valuable in this league. No single correct answer. Many models exist and none solves it fully.
- Own sessions, no parallel work. Deep research: existing systems, expert methods, our league's history. Time is not the constraint (user, 2026-10-03).
- User examples: per-game vs season totals (injury-prone stars like Kawhi Leonard, Anthony Davis); projections vs actual stats so far; real-world context (a rookie whose role grows, like Cooper Flagg in 2025-26: about $20 at the draft, worth about $40 to $50 later); expert systems that drop a player's weakest category and TO and weight scarce categories (Josh Lloyd, Basketball Monster; details not verified); league psychology (early-season hype changes how managers price a player).
- The tool should offer more than one model. The user picks one (for example from a dropdown) or compares them.
- Decisions from the refinement session of 2026-10-04 (user):
  - No paid sources. Not Basketball Monster, not Hashtag.
  - A value has four independent pickers: projection source (Yahoo, ESPN, own, average of sources), basis (per game, totals = per game x projected GP, last season actual), model, dollar conversion (plain or SAVOR).
  - Projected GP goes into the totals basis. Per game stays as its own view.
  - Do not limit the model list. Add every good model we find. Remove a model later if it proves useless.
  - Model list so far: classic z-score; punt z-score; Minus-1 (drop each player's worst category, Basketball Monster definition); DURANT approximation (Minus-1, no TO; the real formula is closed); G-score (adds week-to-week variance, arXiv 2307.02188, needs game logs); H-score (value that depends on my current team, arXiv 2409.09884, open source tool zer2.github.io/fantasy-basketball-optimizer, license not checked); SAVOR dollar conversion (cheap players are worth less because they are replaced from waivers); balance score; market (Yahoo average cost, ESPN average auction price, our league's 2025-26 prices); "fluff" indicator (9-cat rank vs fantasy points rank); reliability score from 3 seasons of GP.
  - Own projection engine (T-025): we build our own projections from all sources, past stats and the expert notes. Output per player: floor, median and ceiling scenarios, then our own dollar projection. Other sources stay as comparison and as a place to find reasons (why a player went up or down).
  - Own projection engine, user ideas (2026-10-04, examples, not the scope; refine in the T-025 session):
    - Minutes are the base. A depth chart per team, if possible with projected minutes. Example: 15 points in 28 minutes last season, now the first option with 32 to 33 minutes, so about 21 points and a most-improved candidate.
    - Team context: teams with no ambition stop playing their good players at some point in the season (shutdown), so expectations drop. Injuries and roster moves (arrivals, departures) open or close minutes in the rotation.
    - Natural growth and decline by age.
    - Fit of roles: several ball-dominant players on one team cannot share the ball, so all of them can drop.
    - Inputs: all numbers, the flow of expert analysis, NBA news and team situations.
  - Inputs from T-026 (2026-10-04, in the DB, refreshed automatically): minutes per game from ESPN, DARKO and FantasyPros; Hashtag depth charts (starter and tier per slot); preseason minutes from stats.nba.com; Vegas season win totals. The spread between the three minutes sources is itself a signal (role not settled). DARKO minutes are 4 to 9 lower than ESPN and FantasyPros for most stars; DARKO says minutes are its weakest stat.
  - Shutdown risk from Vegas (idea for the T-025 session, not decided): our fantasy playoffs are weeks 19 to 21 (late March 2027). Teams with a low win total (now SAC 21.5, BKN 24.5, MIL 26.5, CHI and NOP 27.5) are the ones most likely to rest good players then. So the win total can lower a player's late-season, playoff-week value, not his early value. Also a check: a team's projected minutes should add up to 48 x 5 = 240 per game.
  - T-025 is not last (user, 2026-10-04): the draft should run on our own projections if possible. A first version must be ready before the draft.
  - Backtest: ESPN has a 2025-26 preseason projection. Compare projection against the real season to learn how projections turn into reality, and to score the models.
  - Success measure for a model: weekly H2H simulation. A team that beats weak teams 7-2 but loses 3-6 to strong teams is not a good team. This is not a roto league.
  - Every player gets a value, not only the top 156: the league is played with the whole pool. Known anomalies to solve: stars who fall out of the top 250 in plain 9-cat (Zion Williamson, Antetokounmpo) but never go cheap; low-usage players with no turnovers who rank top 20 but nobody pays for.
  - Reference pool for the average: open. Not top 156 and not a minutes cut alone (user, 2026-10-04): low-minute players who play every game, and backups who produce when the starter is out (example: Paul Reed), belong to the real pool. The pool is a setting; the backtest compares candidates.
  - A model is a function. Every model must run on every base: any season's real stats, any source's projection, our own projection, per game or totals. The user switches the base in a dropdown and the values update at once. Exceptions are inputs, not bases: G-score also needs week-to-week variance from game logs; H-score also needs the draft state; the market "model" is price data.
  - Position does not go into the value. It is a warning only (example: a punt FT% team with 3 or 4 guards loses games in a week when the guards play few games).
  - Evidence for SAVOR in our league: in the 2025-26 auction 27 of 144 players went for $1 and 44 for $3 or less; 8 players went for $50 or more (verified, `draft_picks`).

### Live draft board
- During the draft the board reacts to every event, like a stock market screen.
- User examples: a panel for the nominated player (price range, what he does to my team, how my strategy shifts, players who complement him); my player list ranked by the chosen model, with ranks and prices that move as the draft goes and changes that flash; market tracking (players going above or below reference prices, inflation and deflation, money left at the end is waste); fit-based price limits (a player who fits my build is worth more to me; the tool may also say "do not pay more than $18").

- Decisions from the refinement session of 2026-10-04 (user):
  - Nominated player panel, three layers: numbers (value by each model, price range with live inflation, three thresholds: bargain, fair, stop), fit (my category ranks and H2H table before and after the buy), text (the player's T-022 profile and risk flags).
  - Fit: show the market value, the value for my build, and the number of players left who fill the same need. A small overbid for a fitting player is correct when few alternatives are left. Paying $25 for a $10 player is never correct.
  - Market temperature: track price paid vs model value for every sale. The board tells the user what an expensive or a cheap draft means for the next bids (example 2025-26: Jokić $87, Wembanyama $85, Gilgeous-Alexander $81, but Antetokounmpo, nominated second, went for $62; verified, `draft_picks`).
  - Category scarcity alerts: the board watches my team's weak categories and the supply left in the pool. Example: "your rebounds are low and rebound supply is running out; bid more on the next rebounder". The same for a category that the league used up early (example: assists).
  - The list of signals is open. The tool must see what the user cannot see during a live draft.
  - Price lines per player (user, 2026-10-04): next to bargain, fair and stop, the user's own maximum and minimum ("do not buy above X", "buy at once below Y").
  - Alert and suggestion examples (user, 2026-10-04): good centers are running out and my team needs rebounds; I bought no top-30 player, so punting assists becomes a suggestion; "the assist train is leaving: take Harden, pay 23 instead of 20, or you cannot collect assists later".

### Expert knowledge synthesis (M8 second layer)
- Layer 1 (T-021) only collects: per-video notes with timestamp and quote, no inference. Player and team pages are lists of these notes.
- Layer 2 turns the notes into usable instruments. Short or unclear notes are expanded from the transcript around their timestamp.
- User examples (2026-10-04): article-like pages, not lists. Breakout candidates, bust candidates, late-round flyers (around pick 100 to 110 and later: high upside, low cost, easy to replace from waivers). Draft strategy by stage: early (the first-round player is the core of the team; build around him), middle, late. More categories will come out of the synthesis itself.
- Open: notes only, or notes plus our stats and the LLM's own knowledge (each sentence must show its source); when to run it (after enough videos, together with T-017).
- User example on pick ranges vs auction: pick 110 in a 12-team league is about each team's 9th player. In an auction the mix depends on spend: after paying a lot for two stars (Jokić, Wembanyama), a team may fill 7 or 8 slots with flyers instead of 3 or 4.
- All items above are examples. The list will grow. Refine it in product sessions into tools.
- Decisions from the refinement session of 2026-10-04 (user):
  - Three layers. Layer 1: raw notes (T-021, unchanged). Layer 2: a profile per player and team with two summaries, "durable" and "current". Layer 3: compilations.
  - Profiles state only the latest situation. When a newer note contradicts an older note, the newer note wins and the older one is dropped. No history in the profile (example: Nesmith is a bounce-back candidate now; do not write that he was bad before).
  - Profiles use the notes plus our own stats. Player tips do not wait for T-017. Only price hints wait.
  - First compilations: one sheet per punt build (FT%, AST, TO and others) with the players who fit; breakout candidates; bust candidates; late-round flyers; injury, shutdown and trade risk; auction tactics; strategy by draft stage. Players in a compilation show their T-017 values.
  - The compilation list is open on purpose. While reading the notes, the LLM proposes new articles from patterns it finds, also ones nobody asked for. After the first synthesis, run one more pass that looks for new links across profiles and compilations. Keep this door open in every later session.
  - The LLM for the synthesis can run at the highest setting.
  - Two axes for notes and tags. Axis 1: durable or current. Axis 2: fact or verdict. Facts stay until a newer fact replaces them. For verdicts the newest wins.
  - A short-term call does not define the player (example: a "drop" call after two bad months must not hide that he can play like a top-60 player later). Short-term calls live in the current channel only.
  - Tags: structured data, not text. Each tag has a name from `docs/GLOSSARY.md`, a channel (durable or current), a date, a source note and an optional end condition. The tag list is open (assist specialist, block specialist, punt FT fit, breakout candidate, injury prone, must add, drop, sell high, buy low and more). A player can have 10 to 15 tags.
  - Tags feed three places: compilations (players with a tag), the draft panel, and a tag filter on the player table (example in season: show all "buy low" players).
  - No default time limit on current notes. A note gets an end only when the source gives one: a date ("good schedule for the next 3 weeks") or an event ("until player X returns").
  - `docs/GLOSSARY.md` holds every term and tag with one meaning. Add terms as they appear.
  - Demo feedback (user, 2026-10-04): stats in a table, always all 9 categories plus GP and minutes, also when a model ignores a category. No limit on the number of tags: 1 or 30, as needed. A tag must be useful as a filter or a search (bad example: "two-category player"). Durability tags in both directions (load management, plays every game). The closing note per player can be 2 to 3 sentences.
  - Trial output: `docs/knowledge/_demo/profiles-demo.md`.

### Manager behavior and trades
- Trades are very frequent in this league. Market perception vs model value is a signal.
- User example: sell a player after an early hot streak while managers still price him high.

## Out of scope
- Any write action on Yahoo (add, drop, claim, trade, lineup change, bid).
- Paid data sources (Basketball Monster, Hashtag etc.). User decision 2026-10-04: no payment for any source.
- Hosting on the internet. The site runs on localhost.

## Change rule
A new feature idea goes into this table first, with a phase. Then it can go into `TASKS.md`.
