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
| Yahoo player projections | Projection source | unknown | Check if the API returns projected stats. |
| `nba_api` (stats.nba.com) | Historical player stats, game logs | inferred | Can be rate limited. Cache all responses. |
| NBA schedule JSON (cdn.nba.com) | 2026-27 schedule | inferred | Must find and test the exact URL. |
| Hashtag Basketball (free pages) | Projections, rankings | unknown | Check terms and what is free. |
| Own projection model | Projections | planned | Weighted last 1 to 3 seasons + games played estimate. Used if free sources are not enough. |
| Josh Lloyd, Locked On Fantasy Basketball | Expert digest (M8) | verified (exists) | YouTube: https://www.youtube.com/channel/UC1I9lmlRwqSehJzlRo6DKqg . He is lead analyst at Basketball Monster. |
| YouTube transcripts (`youtube-transcript-api`) | Expert digest (M8) | inferred | Test in P5. |

Rule: when you verify a row, change the status and add the evidence (link or test name).
