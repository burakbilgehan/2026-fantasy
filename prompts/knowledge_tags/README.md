# Tag classifier prompts (T-022)

One call per chunk of up to 60 unknown tag names (`backend/app/jobs/knowledge_run.py`, `classify_all`).
Input: the registry (`docs/knowledge/_data/tags.json`) and the proposals with their uses. Output per proposal: `merge` into an existing tag (alias added), `new` (canonical tag created; several proposals can share one), or `drop` (not a useful filter).
Profiles keep the raw name; the registry maps it at render time, so a merge fixes every profile without a new LLM call. Every decision is logged in `docs/knowledge/_data/tag_decisions.jsonl`.
