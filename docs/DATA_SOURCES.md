# Data sources

Status words: `verified` (checked by a test or a source), `inferred` (likely, not tested), `unknown`.

| Source | Use | Status | Notes |
|--------|-----|--------|-------|
| Yahoo Fantasy API access (all endpoints) | Every Yahoo API call | verified BLOCKED (2026-10-03) | Since 2026-07 Yahoo needs a separate approval. Our app GYvitLgi gets OAuth tokens (verified) and token refresh works without `redirect_uri` (verified), but every API call returns 403 "This application is not authorized to perform this action." Apply: https://sports.yahoo.com/developer/access/ . Context: https://github.com/uberfastman/yfpy/issues/84 . Draft of our application: `docs/yahoo-api-access-application.md`. |
| Yahoo public league pages (`basketball.fantasysports.yahoo.com/nba/23772/...`) | Fallback while API is blocked | verified (2026-10-03) | League is "publicly viewable". `/`, `/settings`, `/draftresults` return 200 without login. Settings and 12 teams parsed (`backend/app/sources/yahoo/web.py`). Logged-out pages show US Eastern time. Unknown: does `/draftresults` update live during an auction? Check Yahoo terms on automated page access. |
| Yahoo Fantasy API `league/{key}/draftresults` | Live draft picks | verified (docs) | No push, no websocket. Poll. During a draft it returns picks made so far. Sources: https://github.com/alienking-sol/live-draft-board , https://yahoo-fantasy-api.readthedocs.io/en/latest/yahoo_fantasy_api.html |
| Yahoo draftresults `cost` field | Auction price per pick | inferred | Must test on last season's league. |
| Yahoo league renew chain (`renew` / `renewed` in settings) | Full league history | inferred | Needed for M4. Must test. |
| Yahoo `transactions` | Trades, adds, drops history | inferred | Read only. |
| Yahoo mock draft via API | Rehearsal | unknown | Probably not visible in the API. Fallback: manual pick entry mode in the draft board. |
| Yahoo player feed `pub-api.fantasysports.yahoo.com/fantasy/v3/players/nba/23772?projected=1&average=1&format=rawjson` | Player ids, projections, last season stats, Yahoo auction value, average cost, eligible positions | verified (2026-10-04) | Public, no login, no API approval. 707 players. Same feed the draft client loads. `projected_stats` = 2026-27 (inferred), `season_stats` = 2025-26 (verified: Cooper Flagg, 2025 draft, 70 GP). Stat ids 0, 3, 4, 6, 7, 10, 12 verified by arithmetic on 1084 stat lines (PTS = 2 FGM + FTM + 3PM). Ids 15 to 19 (REB, AST, STL, BLK, TO) inferred; leaders look right (Jokić AST and REB, Wembanyama BLK, Dončić TO). `rank` column = Yahoo `o_rank` (inferred: overall preseason rank; Jokić = 1). Positions are the league's own set (G, F, C); the mock league feed used PG/SG/SF/PF. `-` = no stats. Undocumented: sync on demand only (`make players-sync`). Code: `app/sources/players/yahoo_pubapi.py`, test `tests/test_players.py`. |
| NBA.com player index (`www.nba.com/players`, `__NEXT_DATA__` JSON) | NBA person ids, current team | verified (2026-10-04) | 620 players on current rosters. Free agents are not listed. 586 of 707 Yahoo players match by name; 0 manual links needed on 2026-10-04. Code: `app/sources/players/nba_index.py`. |
| ESPN site API (`site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/schedule?season=2027&seasontype=2`) | 2026-27 schedule | verified (2026-10-04) | No key. 1200 games, 2026-10-20 to 2027-04-11 (ET dates). 80 games per team: the NBA adds 2 per team after the NBA Cup group stage, so re-sync in December. Date range queries on `/scoreboard` return 400. ESPN abbreviations differ for 6 teams (mapped in `app/sources/teams.py`). Code: `app/sources/schedule/espn.py`. |
| `nba_api` (stats.nba.com) | Historical player stats, game logs | verified BLOCKED (2026-10-04) | Requests time out from this machine, also outside the sandbox. Past seasons need another source. |
| NBA schedule JSON (cdn.nba.com) | 2026-27 schedule | verified BLOCKED (2026-10-04) | `scheduleLeagueV2.json` returns 403 Access Denied from this machine. ESPN is used instead. |
| Hashtag Basketball (free pages) | Projections, rankings | unknown | Check terms and what is free. |
| Own projection model | Projections | planned | Weighted last 1 to 3 seasons + games played estimate. Used if free sources are not enough. |
| Josh Lloyd, Locked On Fantasy Basketball | Expert digest (M8) | verified (exists) | YouTube: https://www.youtube.com/channel/UC1I9lmlRwqSehJzlRo6DKqg . He is lead analyst at Basketball Monster. |
| YouTube transcripts (`youtube-transcript-api`) | Expert digest (M8) | inferred | Test in P5. |

Rule: when you verify a row, change the status and add the evidence (link or test name).
