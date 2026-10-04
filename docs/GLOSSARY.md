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

<!-- tags:start (generated from docs/knowledge/_data/tags.json, do not edit) -->
## Tags
Canonical tag names for profiles (T-022). Other names in brackets are merged into the tag.
Code checks (`app/knowledge/categories.py`): `strong:X` = z >= 2.0 against the top 250 pool, `weak:X` = z <= -1.5 against the pool, `posweak:X` = z <= -1.0 against players of the same position, one of his two weakest categories, and positive value without it (a guard with few blocks is not a punt BLK fit), `bigstrong:X` = F or C with z >= 1.5 against the position, `no3pm` = under 0.3 threes per game, `noweak` = no weak flag at all, `injury` = Yahoo injury status or a note. Basis: 2026-27 projections per game (mean of Yahoo and ESPN); FG% and FT% as volume-weighted impact.

### Category role
- **3PM from a big** [durable]: A forward or center who makes many threes for his position, which helps builds that want threes from the frontcourt.
- **3PM specialist** [durable]: Threes made are a real outlier: far above the top 250 pool. Code check: `strong:3PM`. (merged: 3PM source)
- **AST from a big** [durable]: A forward or center with guard-like assists. Rare, so it helps builds that need assists from the frontcourt. Code check: `bigstrong:AST`.
- **AST specialist** [durable]: Assists are a real outlier: far above the top 250 pool. Code check: `strong:AST`.
- **BLK specialist** [durable]: Blocks are a real outlier: far above the top 250 pool. Code check: `strong:BLK`.
- **elite per game** [durable]: Per game line near the top of the league; his value question is games played, not quality.
- **FG% anchor** [durable]: High FG% on high volume. Lifts a team's FG% clearly. Code check: `strong:FG%`.
- **FG% liability** [durable]: Low FG% on real volume. Hurts a team's FG% clearly. Code check: `weak:FG%`.
- **FT% anchor** [durable]: High FT% on high volume. Lifts a team's FT% clearly. Code check: `strong:FT%`.
- **FT% liability** [durable]: Low FT% on real volume. Hurts a team's FT% clearly; often the reason to punt FT%. Code check: `weak:FT%`. (merged: punt FT anchor)
- **high TO** [durable]: Many turnovers. Hurts the TO category. Code check: `weak:TO`.
- **low TO** [durable]: Few turnovers for his role. Code check: `strong:TO`. (merged: low TO for usage)
- **no 3PM** [durable]: Makes almost no threes. Code check: `no3pm`.
- **PTS specialist** [durable]: Points are a real outlier: far above the top 250 pool, not just a good scorer. Code check: `strong:PTS`.
- **REB specialist** [durable]: Rebounds are a real outlier: far above the top 250 pool. Code check: `strong:REB`.
- **STL specialist** [durable]: Steals are a real outlier: far above the top 250 pool. Code check: `strong:STL`.

### Build fit
- **fits every build** [durable]: No weak category, so he helps any punt build. Code check: `noweak`.
- **Giannis build fit** [durable]: Fits next to Giannis Antetokounmpo in a punt FT% build (Lloyd's build rule).
- **punt 3PM fit** [durable]: Weak in threes for his position, so a punt 3PM team loses little with him. Code check: `posweak:3PM`.
- **punt AST fit** [durable]: Weak in assists for his position, so a punt AST team loses little with him. Code check: `posweak:AST`.
- **punt BLK fit** [durable]: Weak in blocks for his position (not just a guard with few blocks), so a punt BLK team loses little with him. Code check: `posweak:BLK`.
- **punt FG fit** [durable]: Weak in FG% for his position, so a punt FG% team loses little with him. Code check: `posweak:FG%`.
- **punt FT fit** [durable]: Weak in FT% for his position, so a punt FT% team loses little with him. Code check: `posweak:FT%`.
- **punt PTS fit** [durable]: Weak in points for his position, so a punt PTS team loses little with him. Code check: `posweak:PTS`. (merged: low usage)
- **punt REB fit** [durable]: Weak in rebounds for his position, so a punt REB team loses little with him. Code check: `posweak:REB`.
- **punt STL fit** [durable]: Weak in steals for his position, so a punt STL team loses little with him. Code check: `posweak:STL`.
- **punt TO fit** [durable]: Many turnovers for his position, so a punt TO team loses little with him. Code check: `posweak:TO`.

### Role
- **contract year** [current]: In the last year of his contract, so a new deal and a bigger role are at stake this season.
- **minutes competition** [current]: Another player competes for the same minutes; his role is not clear yet. (merged: bench role)
- **minutes limit** [current]: His team or coach holds his minutes below a full starter's load on purpose, even when he is healthy. (merged: coach limits minutes)
- **needs playmaker** [durable]: Not a self-creator. His efficiency depends on a playmaker on the floor with him.
- **new team** [current]: Changed NBA team since last season.
- **role down** [current]: Expected to get fewer minutes, less usage or a smaller role than last season.
- **role up** [current]: Expected to get more minutes, usage or a bigger role than last season.
- **rookie** [current]: First NBA season.
- **two-way contract** [current]: On a two-way contract, so his NBA games and role are limited until he gets a standard deal.
- **unsigned** [current]: Not on any NBA roster now, so his role and value depend on where he signs. (merged: unsigned free agent)
- **usage competition** [current]: Shares the ball with high-usage teammates, which caps his shots and touches even as a starter.
- **usage dependent** [durable]: His fantasy value depends on being a top usage option and drops sharply in a smaller role. (merged: needs high usage)

### Outlook
- **bounce-back** [current]: Expected to recover after one bad season (glossary: Bounce-back). (merged: bounceback, bounce back candidate)
- **breakout** [current]: Expected to produce clearly more than last season (glossary: Breakout). (merged: breakout candidate)
- **bust candidate** [current]: Expected to return clearly less than his draft price. Detail names the site or price when the call is about one site. (merged: bust candidate at Yahoo price, hype-driven value)
- **early-season value** [current]: Expected to produce most early in the season, with value likely to fade later.
- **flyer** [current]: Cheap late pick with high upside, easy to replace if he fails.
- **handcuff** [current]: A backup with real value when the starter ahead of him is out.
- **IL stash** [current]: Injured now but worth drafting late and holding in an IL slot until he returns.
- **regression risk** [current]: A recent jump in shooting or other rates is expected to come back down.
- **sleeper** [current]: The market prices him low and the expert likes him.
- **slow start** [current]: Expected to be limited or weaker early in the season and to produce clearly more later, by the fantasy playoffs. (merged: late-season riser)
- **waiver watch** [current]: Not a draft target in our league, but worth watching on waivers early in the season.

### Risk
- **age decline watch** [durable]: Age makes a drop in minutes or production likely.
- **back-to-back risk** [current]: Expected to sit some back-to-back games this season.
- **consistent** [durable]: His game-to-game production varies very little, so his weekly output is reliable. (merged: consistent producer)
- **cut candidate** [current]: His NBA team may waive him, so he could lose his roster spot and role.
- **foul prone** [durable]: Commits many fouls, which limits his minutes.
- **injury prone** [durable]: Expected to miss games from a chronic or repeated injury (Lloyd: repeated injuries or surgery on the same lower-body part).
- **load management** [durable]: Rests on purpose when healthy, often in back-to-backs. (merged: minutes cap)
- **off-court risk** [durable]: Has off-court problems or past suspensions that can cost games or trust.
- **plays every game** [durable]: Record of very few missed games. (merged: durable)
- **shutdown risk** [current]: His NBA team may stop playing him late in the season.
- **streaky** [durable]: His production or shooting swings between hot and cold stretches, so his weekly output is hard to predict. (merged: streaky shooter)
- **trade risk** [current]: A trade is possible and could lower his role.

### Health
- **injured now** [current]: Has an injury now that can cost games at the start of the season. Code check: `injury`. (merged: offseason surgery)
- **injury last season** [current]: Missed many games last season, so last season's totals understate him.
- **questionable** [current]: Yahoo status questionable or day to day now.

### Market
- **9-cat fluff** [durable]: His 9-cat rank is higher than his real H2H worth (see Nine-cat fluff in the glossary).
- **category league player** [durable]: Worth clearly more in 9-cat category leagues than in points leagues, so points-based rankings and ADP underrate him.
- **expert target** [current]: The expert ranks him clearly above the market and wants to draft him.
- **points league player** [durable]: Worth clearly more in points leagues than in 9-cat. Rankings from points formats overrate him for us. (merged: fluff: overvalued by fantasy points)
- **sites disagree on price** [current]: Yahoo and ESPN prices or ranks differ a lot.
- **undervalued by 9-cat** [durable]: Plain 9-cat rankings rate him lower than his real H2H worth. (merged: fluff: undervalued by 9-cat)

### Schedule
- **bad playoff schedule** [current]: Few games or many back-to-backs in our fantasy playoff weeks (19 to 21).
- **few back-to-backs** [current]: His team has few back-to-backs this season, so rest risk is lower.
- **good playoff schedule** [current]: Many games or few back-to-backs in our fantasy playoff weeks (19 to 21).
- **many back-to-backs** [current]: The team has many back-to-backs this season, so rest risk for its players is higher.

### Expert call
- **buy low** [current]: Trade for him now; other managers price him below his real value.
- **drop** [current]: Not worth a roster spot now. About the present only.
- **must add** [current]: Free agent the expert says every team should add now.
- **sell high** [current]: Trade him now; other managers price him above his real value.

### Team
- **bottom team** [current]: The team is projected to finish near the bottom of the league this season. (merged: bad team, lottery team, projected bottom team, weak team, rebuilding team)
- **concentrated usage** [current]: One or a few stars take most of the team's shots and touches, which caps the usage of everyone else. (merged: one-creator offense)
- **deep rotation** [current]: Many players compete for the team's minutes, so minutes are spread and roles shrink. (merged: crowded rotation, long rotation, crowded backcourt, crowded frontcourt, center committee, low minutes coach, roster overload)
- **defense-first** [durable]: The team is built around defense, with limited offensive creation and spacing.
- **fast pace** [current]: The team plays at a fast pace, which raises its players' counting stats.
- **five-out offense** [durable]: The coach spaces all five players around the arc, so centers and forwards take more threes than usual.
- **heavy starter minutes** [durable]: The coach gives his starters heavy minutes, which raises their counting stats and shrinks bench value.
- **low shutdown risk** [current]: The team is not expected to tank, rest healthy players or shut players down late in the season. (merged: not tanking, win-now team, no tank incentive, low rest risk)
- **new coach** [current]: The team has a new head coach this season, so rotation and minutes habits are less predictable. (merged: new head coach)
- **rookie-averse coach** [durable]: The coach rarely starts or trusts rookies, which caps rookie roles on this team.
- **shared ball handling** [current]: The team has no single lead ball handler, so assists and usage are spread across several players.
- **stable starters** [durable]: The coach rarely changes the starting lineup unless someone is hurt, so starter roles are stable.
- **tank risk** [current]: The team may put draft lottery odds ahead of winning and rest or limit veterans, mostly late in the season.
- **thin rotation** [current]: The team has little depth, so starters carry heavy loads and an injury opens a big role for a reserve. (merged: thin bench, thin depth, thin at guard, thin frontcourt)
- **three-point heavy** [current]: The team takes many threes as a style, which lifts 3PM for its shooters.
- **trades likely** [current]: The front office is expected to make trades this season, which can change roles on the team. (merged: likely to trade, consolidation trade expected, deadline seller)
- **unsettled rotation** [current]: The team's starters or minutes are not settled or change often, so player roles are hard to predict. (merged: unclear rotation, unstable rotation, volatile rotation, high roster turnover)
- **usage freed** [current]: The team lost high-usage players, so the remaining players should get more shots and touches.
- **winning team** [current]: The team is projected to win clearly more than half its games and make the playoffs. (merged: contender, playoff contender, playoff team)

<!-- tags:end -->
