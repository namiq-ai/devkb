#!/usr/bin/env python3
"""devkb guardrail: a PreToolUse hook that reminds the agent to ask devkb before searching code by text.

Fires on the Grep tool, and on a Bash command that runs grep / rg / git grep as a search (not as a filter after a
pipe), when the search touches a repository devkb serves: a directory holding `.devkb/`, the devkb source tree
(`devkb/cli.py`), or the C/C++ corpus under ~/.cache/devkb. Never blocks: it only adds context.
Off when DEVKB_GUARDRAIL=0 (benchmark arms without the guardrail). Every firing is appended to
~/.claude/hooks/devkb-guardrail.log (time, session, tool, repo) so its effect can be measured.

Registered by this repository's `.claude/settings.json` (#126), and possibly also machine-wide in
`~/.claude/settings.json`: a tool call is reminded once however many copies run (a marker per tool call).
"""
import hashlib
import json
import os
import random
import re
import shlex
import sys
import time
from pathlib import Path

REMINDER = ("devkb guardrail: this is a code search in a repository devkb serves ({repo}). For 'where is X defined', "
            "'who calls / uses X', 'what is in this file' or 'what does a change to X touch', ask devkb first "
            "(`devkb symbol|uses|outline|pack ... --project {repo}` or the mcp__devkb tools), check its answer against "
            "the source, and log the query and verdict in the task's dogfood log. grep stays right for filtering "
            "output, literal strings, and checking an edit.")
SEARCH = re.compile(r"(?:^|[;&|(]\s*|\bxargs\s+)(?:git\s+grep|grep|egrep|rg)\b")


def served_repo(path: Path) -> Path | None:
    try:
        p = path.expanduser().resolve()
    except OSError:
        return None
    cache = (Path.home() / ".cache" / "devkb").resolve()
    for d in [p, *p.parents]:
        if d == cache:
            return None
        if d.parent == cache / "cpp-corpus" or (d / ".devkb").is_dir() or (d / "devkb" / "cli.py").is_file():
            return d
    return None


def search_segments(cmd: str) -> list[str]:
    """The pipeline stages that search: a grep after `|` filters another command's output and does not count."""
    out = []
    # words inside quotes are text (a commit message, an echo), not a command: blank them before looking for a search
    cmd = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "", cmd, flags=re.S))
    for part in re.split(r"&&|\|\||;|\n", cmd):
        stages = [s.strip() for s in part.split("|")]
        if SEARCH.search(stages[0]) or any(s.startswith("xargs") and SEARCH.search(s) for s in stages[1:]):
            out.append(part)
    return out


def bash_dirs(cmd: str, cwd: Path) -> list[Path]:
    dirs = [cwd]
    try:
        words = shlex.split(cmd, comments=True, posix=True)
    except ValueError:
        words = cmd.split()
    for i, w in enumerate(words):
        if w == "cd" and i + 1 < len(words):
            dirs.insert(0, Path(words[i + 1]).expanduser() if words[i + 1].startswith(("/", "~")) else cwd / words[i + 1])
        elif w.startswith(("/", "~/")) and not w.startswith("/dev/"):
            dirs.append(Path(w))
    return dirs


def first_copy(ev: dict) -> bool:
    """True for the first copy of this hook to see this tool call; the others stay silent. Atomic (O_EXCL), so two
    copies running at once cannot both answer. Markers older than a day are cleared."""
    key = ev.get("tool_use_id") or hashlib.sha1(json.dumps([ev.get("session_id"), ev.get("tool_name"), ev.get("tool_input"),
                                                            int(time.time() // 10)], sort_keys=True).encode()).hexdigest()
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / "".join(c for c in key if c.isalnum() or c in "-_")[:80], os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    except OSError:
        return True
    if random.random() < 0.02:
        cutoff = time.time() - 86400
        for m in d.iterdir():
            try:
                if m.stat().st_mtime < cutoff:
                    m.unlink()
            except OSError:
                pass
    return True


def main() -> int:
    if os.environ.get("DEVKB_GUARDRAIL", "1") == "0":
        return 0
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input") or {}
    cwd = Path(ev.get("cwd") or os.getcwd())
    if tool == "Grep":
        candidates = [Path(inp["path"]) if inp.get("path") else cwd]
    elif tool == "Bash":
        segs = search_segments(inp.get("command", ""))
        if not segs:
            return 0
        candidates = [d for s in segs for d in bash_dirs(s, cwd)] + bash_dirs(inp.get("command", ""), cwd)[:1]
    else:
        return 0
    repo = next((r for r in map(served_repo, candidates) if r), None)
    if repo is None or not first_copy(ev):
        return 0
    try:
        with open(Path.home() / ".claude" / "hooks" / "devkb-guardrail.log", "a") as fh:
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": ev.get("session_id"),
                                 "tool": tool, "repo": str(repo)}) + "\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": REMINDER.format(repo=repo)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
