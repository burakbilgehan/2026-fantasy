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
| M8 | Expert digest | Ingest Josh Lloyd (Locked On Fantasy Basketball) and other sources. YouTube transcripts. LLM summary: trends, breakouts, waiver picks, schedule tips. | P5 |
| M9 | Season strategy | Weekly matchup outlook. Category targets for the week. Long-term punt and build advice. | P5 |

## Out of scope
- Any write action on Yahoo (add, drop, claim, trade, lineup change, bid).
- Live nomination or live bid data from the Yahoo draft room. We use completed picks only.
- Paid data sources (Basketball Monster etc.), unless the user decides otherwise.
- Hosting on the internet. The site runs on localhost.

## Change rule
A new feature idea goes into this table first, with a phase. Then it can go into `TASKS.md`.
