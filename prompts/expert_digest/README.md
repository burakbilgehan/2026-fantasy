# Expert digest prompts

Everything sent to `claude -p` for one video. The code reads these files at run time (`backend/app/experts/extract.py`). Change them here, nowhere else.

| File | What it is |
|---|---|
| `system.md` | System prompt (`--system-prompt`). |
| `user_prompt.md` | User prompt template, sent on stdin. `{title}`, `{channel}`, `{date}`, `{transcript}` are filled per video. Write any other literal brace as `{{` `}}`. |
| `schema.json` | JSON schema for the answer (`--json-schema`). |
| `config.json` | `model`, `effort`, `prompt_version`, `compatible_versions`. |

## The exact call

```
env -u ANTHROPIC_API_KEY -u CLAUDECODE -u CLAUDE_EFFORT -u 'CLAUDE_CODE_*' \
claude -p --model <config.model> --effort <config.effort> --output-format json \
  --tools '' --no-session-persistence --setting-sources '' --strict-mcp-config \
  --system-prompt "$(cat system.md)" --json-schema "$(cat schema.json)" \
  < <user_prompt.md filled for one video>
```

- Runs on the user's Claude subscription. `ANTHROPIC_API_KEY` is removed, so no API billing.
- No tools, no settings files (no CLAUDE.md), no MCP, no saved session. The child sees only these files and the transcript.
- To see the full call for one video, with the filled prompt: `make expert-prompt VIDEO=<video id>`.

## Transcript format in `{transcript}`

One line per 30 seconds: `[m:ss] text`. Auto captions, no names list. Player names are resolved after the call (`backend/app/experts/match.py`).

## Versions

- Change that should redo old videos: raise `prompt_version`.
- Change that keeps old notes valid: add the new number to `compatible_versions` too.
- Every note file stores `prompt_version` and `prompt_sha` (hash of the three prompt files).

| Version | Change |
|---|---|
| 1 | Sonnet, full player list in the prompt. |
| 2 | Opus medium. No player list. |
| 3 | No nickname list. `team` field on player notes. |
