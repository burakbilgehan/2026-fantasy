Write the profile of the NBA team {team} for fantasy managers in our league. Today is {today}.

A team profile answers: how does this team change the fantasy value of its players? Pace and style, minutes and rotation (depth, who starts, minutes caps, coach habits), usage and who handles the ball, team strength and the risk of tanking or resting players late in the season, the schedule (back-to-backs, fantasy playoff weeks), trades that may happen.

# Rules

Statements go into two channels:
- current: things that can change soon. Rotation and depth chart, roles, injuries, trade talk, team outlook this season, schedule this season.
- durable: things that stay true for a long time. Coach habits (rest, minutes, pace), style of play, how the team uses positions.

Each statement is a fact or a verdict. Split mixed sentences.
- No history. Write the situation now. A fact stays until a newer fact replaces it. For verdicts on the same question, the newest note wins.
- Give `until` only when a note names an end (a date or an event). Never invent an end.
- Merge notes that say the same thing into one statement. Cite all of them.

Sources:
- Every statement and every tag cites the ids of the team notes it rests on, like "aBc123:t2", or "stats" for the number table, the depth chart and the roster list.
- The reader sees the table. Do not write statements that only restate it. Use it when it supports a point (example: "few back-to-backs, so less rest risk for its stars").
- `date` = the date of the newest note cited (YYYY-MM-DD). For "stats"-only use today.

Tags:
- Use the names from the tag list exactly; put specifics in `detail`. Category tags (specialist, anchor, liability, punt fit) are for players: never use them on a team.
- Team tags must help find a group of teams: "all teams with a good playoff schedule", "all tanking teams", "all teams with a deep rotation".
- If no listed tag fits a point worth filtering on, make a new short generic tag and give its meaning in `new_meaning`. Never make a new name for a meaning a listed tag covers.

Note:
- 2 to 3 sentences: what this team means for our draft and season. Which of its players gain or lose, and what to watch early.

# Tag list

{tag_list}

# Numbers (from our database)

{numbers}

# Players of this team with a profile, and their tags

{roster}

# Team notes about {team}

Newest video first. Format: [id] (horizon) text.

{team_notes}
