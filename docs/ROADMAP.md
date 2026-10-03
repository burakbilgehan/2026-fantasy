# Roadmap

Fixed date: auction draft on 2026-10-18. NBA season starts after the draft.

| Phase | Target date | Content | Exit condition |
|-------|-------------|---------|----------------|
| P0 | 2026-10-08 | M0 core platform. Yahoo OAuth (read). Sync league settings, teams, players. NBA stats and schedule sync. | `make dev` starts backend and frontend. League settings show on the page with real data. |
| P1 | 2026-10-14 | M1 player value table. M2 live draft board. Last season's auction prices from Yahoo. | Board follows a real or mock draft with 3 to 5 s delay. Price ranges change with inflation. |
| P2 | 2026-10-17 | Draft rehearsal on a Yahoo mock draft (or manual entry mode). Fix issues. | User does one full rehearsal and accepts the tool. |
| P3 | 2026-10-31 | M3 league dashboard. M4 manager profiles from full league history. | H2H matrix and manager pages show real data. |
| P4 | 2026-11-30 | M5 trade analyzer. M6 free agent scout. M7 schedule planner. | Each widget works on real league data. |
| P5 | later | M8 expert digest. M9 season strategy. | To be defined. |

Rule: P0 to P2 have priority over all other work until 2026-10-18.
