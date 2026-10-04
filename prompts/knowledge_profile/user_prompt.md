Write the profile of {name} ({team}, {position}). Today is {today}.

# Rules

Statements go into two channels:
- current: things that can change soon. Role, minutes, team situation, health now, form, price and rank calls, buy or sell advice, schedule this season.
- durable: things that stay true for a long time. Skills, category profile (strong and weak categories), playing style, injury history.

Each statement is a fact or a verdict:
- fact: something that happened or is the case (a trade, an injury, a signing, a depth chart position).
- verdict: an opinion, a projection or advice (a rank, "should bounce back", "do not draft before round 5").
- Split mixed sentences: one fact statement and one verdict statement.

Latest state only:
- No history. Write the situation now. Do not write that he "was" bad and "is now" good; write only what is true now.
- A fact stays until a newer fact replaces it. Drop facts that a newer note shows are no longer true (example: "may be traded" after a note that he was traded).
- For verdicts on the same question, the newest note wins. Drop the older verdict. If two notes from about the same time disagree, write one statement that says the experts disagree.
- A short-term call (drop, sell high) stays in current and does not change the durable picture.
- A verdict that depends on a condition ("top 100 if his FG% returns") is current, not durable.
- Give `until` only when a note names an end: a date ("for the next 3 weeks", "until Thanksgiving") or an event ("until X returns"). Otherwise leave it empty. Never invent an end.
- Merge notes that say the same thing into one statement. Cite all of them.

Sources:
- Every statement and every tag cites the ids of the notes it rests on, like "aBc123:p4". Team notes have ids like "aBc123:t2".
- Use "stats" as a source when the statement rests on the number tables or the category profile.
- The reader sees the tables. Do not write statements that only restate them: no "Yahoo ranks him below ESPN", no "he was not drafted in our league last season", no "he played 45 games". Use numbers in the Note, where they support a conclusion.
- Durable category statements describe real outliers only (see the category profile). "Average blocks for a guard" is not worth a statement.
- Notes are from video transcripts. Some name a team that has changed; the profile header has the current team.
- Team notes are context for the whole team. Use one only when it changes this player's outlook.
- `date` of a statement = the date of the newest note it cites (YYYY-MM-DD). For a "stats"-only statement use today.

Tags:
- A tag is a filter. It must help find a group of players: "all punt FT fits", "all bounce-back players", "all trade risks".
- Use the names from the tag list below exactly. Put specifics in `detail` (example: tag "injury prone", detail "repeated knee surgery").
- Use as many tags as fit, 1 or 30. Do not add a tag the notes or the tables do not support.
- Category tags need a real outlier. Code checks them against the category profile and removes the ones that do not pass:
  - "X specialist", "FG% anchor", "FT% anchor", "low TO": only for a category flagged "league outlier, strong". A good scorer is not a "PTS specialist"; a player whose best category is far above the league is.
  - "FG% liability", "FT% liability", "high TO": only for "league outlier, weak".
  - "punt X fit": only for a category flagged "weak for his position (punt fit)". Code flags at most his two weakest categories, and only when he keeps real value without them. A guard with few blocks is normal for a guard and is not a punt BLK fit. A player weak in many categories is a low value player, not a fit for many punt builds. No flag means no punt fit tag.
  - "fits every build": only when no category is flagged weak.
- "injured now": only when the Yahoo injury status is set or a note says he is injured now.
- If no listed tag fits a point that is worth filtering on, make a new tag: a short generic name that other players could also get, and its meaning in one sentence in `new_meaning`. Never make a new name for a meaning that a listed tag already covers. For listed tags, leave `new_meaning` empty.

Note:
- 2 to 3 sentences: what this means for our league. Use the prices (Yahoo, ESPN, our league's last auction) and ranks, the builds he fits, and what to check early in the season.

# Tag list

{tag_list}

# Numbers (from our database)

Stats are per game. FG% and FT% show attempts per game in brackets. Past seasons are actual NBA stats; "proj" rows are site projections for {season}.

{stat_table}

{price_table}

Yahoo injury status now: {injury}

# Category profile (computed by code)

Basis: {season} projections per game (mean of Yahoo and ESPN). z vs pool: against the top 250 players. z vs position: against players of his position ({groups}). FG% and FT% z use volume-weighted impact. TO z is flipped: a negative z means many turnovers.

{category_profile}

# Expert notes about {name}

Newest video first. Format: [id] (horizon) text. Value: value hint.

{player_notes}

# Team notes about {team}

{team_notes}
