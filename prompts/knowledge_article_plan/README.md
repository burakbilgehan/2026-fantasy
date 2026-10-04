# Article plan prompt (T-022)

One call. Input: all verified method notes (ids `{video_id}:r{i}`), tag counts from `knowledge_tags`, the user's required list (`REQUIRED` in `backend/app/knowledge/articles.py`). Output: the article list, compilations with tags, topics with method note ids, extra articles marked `proposed`. Saved in `docs/knowledge/_data/articles/_plan.json`; reused until `make knowledge-articles ARGS=--replan`.
