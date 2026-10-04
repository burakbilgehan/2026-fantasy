# Glossary

Terms from fantasy basketball, from the experts we follow, and from our own tool. One meaning per term.
Add a term when you meet it in a note, a source or a session. Tags used on players (T-022) must have an entry here.

## Expert calls (short-lived, change during the season)
- **Must add**: a free agent the expert says every team should pick up now.
- **Add / stash**: worth a roster spot. "Stash" = hold him now for value that comes later (injury return, role change).
- **Drop**: not worth a roster spot now. A drop call is about the present; it does not describe the rest of the season.
- **Hold**: keep the player in spite of bad recent games.
- **Sell high**: trade the player away now, because other managers price him above his real value (often after a hot shooting streak).
- **Buy low**: trade for the player now, because other managers price him below his real value (often after a cold streak or an injury).
- **Streamer**: a player you hold for a few days only, for his games in that week.

## Outlook (before or during a season)
- **Breakout**: a player expected to produce clearly more than last season, usually from more minutes or a bigger role.
- **Bust**: a player expected to return clearly less than his draft price.
- **Bounce-back**: a player expected to recover after one bad season.
- **Sleeper**: a player the market prices low and the expert likes.
- **Flyer**: a cheap late pick with high upside. Easy to replace from waivers if he fails.
- **Handcuff**: a backup who gets a big role and real value when the starter ahead of him is out (example: Paul Reed in 2025-26).
- **Load management**: a healthy player rests on purpose, often in back-to-backs.
- **Shutdown risk**: his NBA team may stop playing him late in the season (team out of the race, minor injuries).
- **Depth chart**: a team's players per position slot (PG, SG, SF, PF, C), starter first. In our data from Hashtag Basketball, with a tier per player (1 = starter, 2 = second unit, then 3 and 4). Several players can share a tier.
- **Projected minutes (MPG)**: minutes per game a source expects a player to play. Base of our own projection (T-025).
- **Win total**: the betting line for a team's season wins (over/under). We use it as a sign of team strength and of late-season rest risk.
- **Injury prone**: the expert expects missed games. Lloyd's rule: repeated injuries or surgery on the same lower-body part.

## Strategy
- **Punt**: ignore one or more categories on purpose to be stronger in the others. Not the same as trying to be bad in them.
- **Build**: the set of categories a team tries to win (example: punt FT% build).
- **Stars and scrubs**: auction plan with two or three expensive stars and many $1 players.
- **Balanced**: auction plan that spreads the budget over many mid-price players.
- **Streaming**: using one or more roster spots for short-term pickups to play more games per week.
- **Nine-cat fluff** (Lloyd): a player whose 9-cat rank is higher than his real worth, because the z-score sum rewards low turnovers, steals or one extreme category.
- **Quality game** (Lloyd): a game on a day with few NBA games, so the player surely fits in the lineup.

## Market and auction
- **ADP**: average draft position in snake drafts on a site.
- **Average cost / average auction price**: mean price of the player in auction drafts on a site.
- **Inflation**: prices in this draft compared with reference values. Above 1.0 = players go for more than reference.
- **Replacement level**: the value of the best player who is free on waivers. Value above this level is what a team pays for.
- **FAB**: free agent budget, the money for waiver bids during the season.

## Valuation models
- **Z-score**: (player stat minus pool average) / pool standard deviation, per category, then the sum. The classic method (Basketball Monster, Hashtag).
- **Minus-1**: z-score sum without the player's own worst category (Basketball Monster definition).
- **DURANT**: Josh Lloyd's ranking for H2H at Basketball Monster. Per game, no turnovers, corrects fluff. Exact formula is not public.
- **G-score**: z-score with week-to-week variance added to the denominator. Noisy categories (steals, percentages, turnovers) weigh less. Source: arXiv 2307.02188.
- **H-score**: value of a player given my current team and the draft state. Finds punts by itself. Source: arXiv 2409.09884.
- **SAVOR**: streaming-adjusted value over replacement. Dollar conversion that lowers cheap players, because they are replaced during the season.

## Our own terms
- **Durable**: note or tag that stays true for a long time (skills, category profile, injury history).
- **Current**: note or tag that can change soon (role, form, health, expert calls).
- **Fact**: something that happened or is the case (a trade, an injury). Stays until a newer fact replaces it.
- **Verdict**: an opinion or advice (draftable, drop). The newest verdict replaces the older one.
