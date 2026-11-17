"""`devkb hook pre-edit`: a Claude Code PreToolUse hook that puts the file's pack in front of the agent at its first edit.

Agents that are told to run `pack` before editing mostly do not: they read code to learn how it is written, and the
instruction waits for a moment they never notice. The hook does not wait for the agent to choose. When an agent is
about to Edit or Write a file the graph knows, or runs a shell command that names one, it runs `devkb pack file PATH` and returns the answer as extra context
for that one tool call: the functions other files call (so the change keeps them working), the files that depend on
it, the tests to run. It never blocks the edit, never fails the session, and gives a file at most once per session.

Wired by the plugin (plugins/devkb/hooks/hooks.json) or by `devkb init --claude-hook` (.claude/settings.json).
Reads the hook event on stdin; writes `hookSpecificOutput.additionalContext` on stdout when there is something to say.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
LIMIT = 6000
BASH_FILES = 2   # a shell command gets the packs of at most this many files it mentions
_PATH = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|ts|tsx|js|mjs|c|cc|cpp|cxx|h|hh|hpp|hxx|inl|java|go|rs))(?![\w/-])")
HEADER = ("devkb pack for `{rel}`, run for you before this edit (each item carries the line that proves it; a pack "
          "marked Complete needs no second search, one marked Incomplete says where to look):\n\n")


def _project(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()


def _seen(project: Path, session: str, rel: str, mark: bool) -> bool:
    """True when this session already got the pack for this file. Records it when `mark`."""
    if not session:
        return False
    log = project / ".devkb" / ".hook-seen" / "".join(c for c in session if c.isalnum() or c in "-_")[:80]
    try:
        done = set(log.read_text().splitlines()) if log.exists() else set()
        if rel in done:
            return True
        if mark:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as fh:
                fh.write(rel + "\n")
    except OSError:
        pass
    return False


def _pack(project: Path, rel: str, session: str, timeout: float) -> str | None:
    """The framed pack for one tracked file the graph knows, once per session; None when there is nothing to say."""
    path = project / rel
    if not path.is_file() or not (project / ".devkb" / "nodes.jsonl").exists() or _seen(project, session, rel, mark=False):
        return None
    proc = subprocess.run(
        [sys.executable, "-m", "devkb.cli", "pack", "--project", str(project), "file", rel],
        capture_output=True, text=True, timeout=timeout, cwd=str(project), check=False,
    )
    text = proc.stdout.strip()
    if proc.returncode != 0 or not text or "The graph has no code" in text:
        return None
    _seen(project, session, rel, mark=True)
    if len(text) > LIMIT:
        text = text[:LIMIT].rsplit("\n", 1)[0] + "\n... (cut; run `devkb pack --project . file " + rel + "` for the rest)"
    return HEADER.format(rel=rel) + text


def _answer(parts: list[str]) -> dict | None:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n\n".join(parts)}} if parts else None


def pre_edit(event: dict, timeout: float = 25.0) -> dict | None:
    """The hook's JSON answer for one event, or None when there is nothing to add.

    Edit and Write: the pack of the file about to change. Bash: agents mostly read with `cat` and `sed` and change files
    with a script, never with Edit (0 of 6 builds in the C++ exercise edited an existing file with it), so the packs of
    up to BASH_FILES tracked source files the command names are given instead."""
    tool, given = event.get("tool_name"), (event.get("tool_input") or {})
    project, session = _project(event), event.get("session_id", "")
    if tool in EDIT_TOOLS:
        raw = given.get("file_path") or given.get("notebook_path")
        if not raw:
            return None
        path = Path(raw)
        try:
            rel = (path if path.is_absolute() else project / path).resolve().relative_to(project).as_posix()
        except ValueError:
            return None  # outside the project
        return _answer([x for x in [_pack(project, rel, session, timeout)] if x])
    if tool == "Bash":
        parts: list[str] = []
        tried: set[str] = set()
        for m in _PATH.finditer(given.get("command") or ""):
            try:
                rel = (project / m.group(1)).resolve().relative_to(project).as_posix()
            except ValueError:
                continue
            if rel in tried:
                continue
            tried.add(rel)
            text = _pack(project, rel, session, timeout)
            if text:
                parts.append(text)
            if len(parts) >= BASH_FILES:
                break
        return _answer(parts)
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] != ["pre-edit"]:
        print("usage: devkb hook pre-edit   (reads a Claude Code PreToolUse event on stdin)", file=sys.stderr)
        return 2
    try:
        out = pre_edit(json.loads(sys.stdin.read() or "{}"))
        if out:
            print(json.dumps(out))
    except Exception as exc:  # a hook must never break the session
        print(f"devkb hook: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
