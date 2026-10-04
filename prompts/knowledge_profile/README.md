# Knowledge profile prompts (T-022)

Everything sent to `claude -p` for one player profile. Code: `backend/app/knowledge/profile.py`. Run: `make knowledge-run`.

| File | What it is |
|---|---|
| `system.md` | System prompt: league rules, source rules. |
| `user_prompt.md` | Template. Filled per player: tag list, stat and price tables, category profile, notes with ids. Literal braces as `{{` `}}`. |
| `schema.json` | Answer schema: current and durable statements (fact or verdict, date, until, sources), tags, note. |
| `config.json` | `model`, `effort`, `prompt_version`, `compatible_versions`. |

The call is the same as `expert_digest` (see its README): no tools, no settings, no API key.

After the call, code checks the answer:
- Source check: statements and tags must cite note ids from the input or `stats`; others are rejected.
- Tag gate: category tags (specialist, anchor, liability, punt fit, ...) must pass the code check of their rule in `docs/knowledge/_data/tags.json` (`app/knowledge/categories.py`). Applied at render time.
- Unknown tag names go to the classifier (`prompts/knowledge_tags/`).

## Versions

| Version | Change |
|---|---|
| 1 | Pilot (14 players). |
| 2 | Full league rules in the system prompt (playoffs end 2027-03-28). Category profile block and rules for category tags. No statements that restate the tables. Conditional verdicts are current. |
| 3 | Punt fit: at most the two weakest categories, and only with value left without them (user, 2026-10-04). |
