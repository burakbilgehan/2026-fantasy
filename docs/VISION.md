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

### Live draft board
- During the draft the board reacts to every event, like a stock market screen.
- User examples: a panel for the nominated player (price range, what he does to my team, how my strategy shifts, players who complement him); my player list ranked by the chosen model, with ranks and prices that move as the draft goes and changes that flash; market tracking (players going above or below reference prices, inflation and deflation, money left at the end is waste); fit-based price limits (a player who fits my build is worth more to me; the tool may also say "do not pay more than $18").

### Expert knowledge synthesis (M8 second layer)
- Layer 1 (T-021) only collects: per-video notes with timestamp and quote, no inference. Player and team pages are lists of these notes.
- Layer 2 turns the notes into usable instruments. Short or unclear notes are expanded from the transcript around their timestamp.
- User examples (2026-10-04): article-like pages, not lists. Breakout candidates, bust candidates, late-round flyers (around pick 100 to 110 and later: high upside, low cost, easy to replace from waivers). Draft strategy by stage: early (the first-round player is the core of the team; build around him), middle, late. More categories will come out of the synthesis itself.
- Open: notes only, or notes plus our stats and the LLM's own knowledge (each sentence must show its source); when to run it (after enough videos, together with T-017).
- User example on pick ranges vs auction: pick 110 in a 12-team league is about each team's 9th player. In an auction the mix depends on spend: after paying a lot for two stars (Jokić, Wembanyama), a team may fill 7 or 8 slots with flyers instead of 3 or 4.
- All items above are examples. The list will grow. Refine it in product sessions into tools.

### Manager behavior and trades
- Trades are very frequent in this league. Market perception vs model value is a signal.
- User example: sell a player after an early hot streak while managers still price him high.

## Out of scope
- Any write action on Yahoo (add, drop, claim, trade, lineup change, bid).
- Paid data sources (Basketball Monster etc.), unless the user decides otherwise.
- Hosting on the internet. The site runs on localhost.

## Change rule
A new feature idea goes into this table first, with a phase. Then it can go into `TASKS.md`.
