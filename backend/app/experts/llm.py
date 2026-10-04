"""LLM calls through the local `claude -p` CLI (the user's subscription, no API key).

The child process gets a clean environment and context:
- ANTHROPIC_API_KEY removed, so the CLI uses the subscription login.
- CLAUDECODE, CLAUDE_EFFORT and CLAUDE_CODE_* removed, so a run from inside a
  Claude Code session works and does not inherit that session's settings.
- No tools, no settings files, no MCP servers, no saved session. Without
  `--setting-sources ""` the child loads the user's CLAUDE.md files (verified
  2026-10-04: it then replied in Turkish and added connector notices).
- cwd is a temp folder, so no project files are in reach.
Structured output: `--json-schema` + `--output-format json`; the parsed object
is in the `structured_output` field of the result (verified 2026-10-04).
"""

import json
import os
import re
import signal
import subprocess
import tempfile
import threading


class LlmError(Exception):
    pass


class UsageLimit(LlmError):
    """The subscription usage limit is reached. Retrying now does not help."""


# The CLI's text when the subscription limit is hit (inferred from the CLI's wording,
# not seen yet): "Claude AI usage limit reached", "You've hit your limit".
_LIMIT = re.compile(r"usage limit|hit your (session )?limit|limit reached", re.I)

_ACTIVE: set[subprocess.Popen] = set()
ABORTED = threading.Event()  # set by kill_all: no new calls start
_LOCK = threading.Lock()


def kill_all() -> None:
    """Kill every running claude child (hard stop). Safe from any thread."""
    ABORTED.set()
    with _LOCK:
        procs = list(_ACTIVE)
    for p in procs:
        try:
            os.killpg(p.pid, signal.SIGKILL)  # own session: pid = process group id
        except (ProcessLookupError, PermissionError):
            pass


def command(system: str, schema: dict, model: str, effort: str) -> list[str]:
    """The exact argv. The prompt goes in on stdin."""
    return [
        "claude", "-p", "--model", model, "--effort", effort, "--output-format", "json",
        "--tools", "", "--no-session-persistence", "--setting-sources", "",
        "--strict-mcp-config", "--system-prompt", system,
        "--json-schema", json.dumps(schema),
    ]


def run_json(prompt: str, system: str, schema: dict, model: str = "opus",
             effort: str = "medium", timeout: int = 900) -> tuple[dict, dict]:
    """Return (structured output, usage info)."""
    if ABORTED.is_set():
        raise LlmError("aborted")
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_EFFORT")
           and not k.startswith("CLAUDE_CODE_")}
    cmd = command(system, schema, model, effort)
    with tempfile.TemporaryDirectory() as cwd:
        # Own session: a terminal Ctrl-C reaches only our process, which decides
        # whether to wait for this call or stop it (kill_all).
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, cwd=cwd,
                                start_new_session=True)
        with _LOCK:
            _ACTIVE.add(proc)
        try:
            stdout, stderr = proc.communicate(prompt, timeout=timeout)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            with _LOCK:
                _ACTIVE.discard(proc)
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError as e:
        text = stderr[-500:] or stdout[-500:]
        raise (UsageLimit if _LIMIT.search(text) else LlmError)(
            f"claude exit {proc.returncode}: {text}") from e
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        text = str(out.get("result"))[:500]
        raise (UsageLimit if _LIMIT.search(text) else LlmError)(f"claude error: {text}")
    usage = {"model": next(iter(out.get("modelUsage") or {}), model), "effort": effort,
             "cost_usd_list": out.get("total_cost_usd"), "duration_ms": out.get("duration_ms")}
    return out["structured_output"], usage
