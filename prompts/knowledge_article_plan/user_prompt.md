Plan the articles of the knowledge base. Today is {today}.

The knowledge base has player profiles with tags, team profiles, and {rule_count} general method notes from expert videos (below). Articles turn this into tools for our draft (2026-10-18) and our season.

There are two article types:
- compilation: a list of players selected by tags, grouped into tiers, with a short line per player. Give `tags` (exact canonical tag names from the tag counts below; a player qualifies when he has any of them).
- topic: a strategy or method article built from the method notes. Give `rule_ids`: the ids of every method note the article needs (no limit; include all that are on topic).

Required articles (the user asked for these; keep each one, you may split one into several):
{required}

Then propose more articles from patterns you see in the method notes and in the tag counts: subjects the experts return to often, rules that change how to draft or manage in our league, tag groups that make a useful list. Only propose an article that a manager in our league would open during the draft or the season. Mark these `proposed: true`. Do not propose an article that repeats a required one.

For each article give a short `slug` (lowercase, hyphens), a `title`, and in `brief` two sentences: what the article must answer for our league.

# Tag counts (players per tag, after the category check)

{tag_counts}

# Method notes

Format: [id] date: text

{rules}
