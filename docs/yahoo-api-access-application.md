# Yahoo Fantasy Sports API access application (draft)

Form: https://sports.yahoo.com/developer/access/
Status: not submitted. The user must fill the personal fields and submit.

Why: since 2026-07 Yahoo gates the Fantasy API. Our app gets 403
"This application is not authorized to perform this action." on every endpoint
(verified 2026-10-03). Context: https://github.com/uberfastman/yfpy/issues/84

| Field | Value |
|---|---|
| Name | (you) |
| Business Title | Individual developer (personal project) |
| Email Address | (you) |
| Phone Number | (you) |
| Business Name & Address | Individual, no company. (your address) |
| Consumer-Facing Product or App Name | 2026-fantasy (personal league dashboard, not public) |
| Brief Company Description | No company. I am one person building a private, local analysis tool for my own Yahoo Fantasy Basketball league. |
| Website URL or App Store Details | Not public. Runs only on localhost. Private repo: https://github.com/burakbilgehan/2026-fantasy |
| Expected Users | Small (< 1,000 users). Real number: 1. |
| Client ID | dj0yJmk9UkZmMGFLRllQUlVaJmQ9WVdrOVIxbDJhWFJNWjJrbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PWYw (app "2026-fantasy-read", App ID GYvitLgi) |

Describe Your Intended Use Case:

> Personal, single-league, read-only use. I am a manager in one private Yahoo Fantasy Basketball league (NBA, league ID 23772, 12 teams, head-to-head 9 categories, auction draft on 2026-10-18). I am building a local dashboard that runs only on my own computer and is used only by me.
>
> Data I need to read: league settings, teams and managers, rosters, draft results including auction cost (live during our draft and for past seasons of the same league), transactions (trades, adds, drops), matchups and scoreboard, players and player stats, and the league renew chain to read past seasons of this league.
>
> I use it to value players for the auction, track the live draft, and evaluate trades. The tool never writes to Yahoo: no adds, drops, trades or bids. I make every move by hand on Yahoo. Data is not shared, sold or published. Polling is light: during the 2-hour draft, one draftresults request every 3 to 5 seconds; otherwise a few requests per day.

Additional Notes:

> Read-only access is enough. Our auction draft is on 2026-10-18. If possible, I would be grateful for a review before that date.
