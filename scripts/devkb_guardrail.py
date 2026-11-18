#!/usr/bin/env python3
"""devkb guardrail: a PreToolUse hook that reminds the agent to ask devkb before searching code by text.

Fires on the Grep tool, and on a Bash command that runs grep / rg / git grep as a search (not as a filter after a
pipe), when the search touches a repository devkb serves: a directory holding `.devkb/`, the devkb source tree
(`devkb/cli.py`), or the C/C++ corpus under ~/.cache/devkb. Never blocks: it only adds context.
Off when DEVKB_GUARDRAIL=0 (benchmark arms without the guardrail). Every firing is appended to
~/.claude/hooks/devkb-guardrail.log (time, session, tool, repo) so its effect can be measured.

Registered by this repository's `.claude/settings.json` (#126), and possibly also machine-wide in
`~/.claude/settings.json`: a session is reminded once, at its first code search, however many copies run.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PENDING = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-pending"

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


def first_of_session(ev: dict) -> bool:
    """One reminder per session (#126 measurement: about 12 per run were ignored, so more add cost, not use)."""
    sid = "".join(c for c in str(ev.get("session_id") or "") if c.isalnum() or c in "-_")[:80]
    if not sid:
        return True
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / f"session-{sid}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    except OSError:
        return True
    return True


def bash_pattern(command: str) -> str:
    """The pattern of the first grep / rg in a command: the `-e` value, else the first word that is not an option."""
    try:
        words = shlex.split(command, comments=True)
    except ValueError:
        return ""
    for i, w in enumerate(words):
        if w in ("grep", "egrep", "rg"):
            words = words[i + 1:]
            break
    else:
        return ""
    for i, w in enumerate(words):
        if w == "-e" and i + 1 < len(words):
            return words[i + 1]
        if not w.startswith("-"):
            return w
    return ""


SUBSTITUTED = ("devkb answered this search from the graph: every name it asks about resolved, with coverage Complete, "
               "so this is the search's result (grep was not needed).\n\n{answers}\n\n(For grep's raw lines as well, "
               "repeat the identical command: a repeat runs as a plain search.)")
ALONGSIDE = ("devkb's answer for the names this search asks about (resolved, coverage Complete); the command still "
             "ran.\n\n{answers}")
MAX_ANSWER = 8000


def pure_search(tool: str, inp: dict) -> bool:
    """A call that only searches (the Grep tool, or one shell command whose first stage is the search): replacing its
    result loses nothing. Anything else keeps running, with devkb's answer added beside it."""
    if tool == "Grep":
        return True
    cmd = inp.get("command", "")
    return len([p for p in re.split(r"&&|\|\||;|\n", cmd) if p.strip()]) == 1 and bool(search_segments(cmd))


def again(ev: dict, inp: dict) -> bool:
    """True the second time this session makes exactly this search: the agent asked for the raw matches."""
    sid = "".join(c for c in str(ev.get("session_id") or "") if c.isalnum() or c in "-_")[:80]
    key = hashlib.sha1(json.dumps([sid, ev.get("tool_name"), inp], sort_keys=True).encode()).hexdigest()
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / f"sub-{key}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return True
    except OSError:
        return True
    return False


def answer_or_record(ev: dict, repo: Path, tool: str, inp: dict, pattern: str) -> dict | None:
    """#131 + #133. Ask devkb about the names the search asks for. Every name resolved and Complete: return devkb's
    answer as the result (a pure search) or beside it (a compound command), in the same call. Otherwise the search runs
    untouched, and the verdict is kept for the PostToolUse hook, which logs the miss if grep finds code."""
    from devkb import misses
    key = "".join(c for c in str(ev.get("tool_use_id") or "") if c.isalnum() or c in "-_")[:80]
    names = misses.navigation_names(pattern)
    if not names or not (repo / ".devkb").is_dir():
        return None
    queries, answers = [], []
    for n in names:
        r = misses.run_query(repo, "change", n)
        if r:
            queries.append({"name": n, "verdict": r[0], "detail": r[1],
                            "query": f"devkb pack change {shlex.quote(n)} --project {shlex.quote(str(repo))}"})
            answers.append(r[2].strip())
    if queries and len(queries) == len(names) and all(q["verdict"] == "complete" for q in queries):
        text = "\n\n".join(answers)
        text = text if len(text) <= MAX_ANSWER else text[:MAX_ANSWER].rsplit("\n", 1)[0] + "\n... (cut)"
        if pure_search(tool, inp):
            if again(ev, inp):
                return None                      # the agent asked for the raw matches: let the search run
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": SUBSTITUTED.format(answers=text)}}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ALONGSIDE.format(answers=text)}}
    if not misses.enabled() or not key or not any(q["verdict"] not in ("complete", "other") for q in queries):
        return None
    built, head = misses.graph_state(repo)
    try:
        PENDING.mkdir(parents=True, exist_ok=True)
        (PENDING / key).write_text(json.dumps({
            "repo": str(repo), "session": ev.get("session_id") or "", "tool": tool, "pattern": pattern, "names": names,
            "queries": queries, "built": built, "head": head, "version": misses.devkb_version()}))
    except OSError:
        pass
    return None


def main() -> int:
    if os.environ.get("DEVKB_GUARDRAIL", "1") == "0":
        return 0
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input") or {}
    cwd = Path(ev.get("cwd") or os.getcwd())
    pattern = ""
    if tool == "Grep":
        pattern = inp.get("pattern", "")
        candidates = [Path(inp["path"]) if inp.get("path") else cwd]
    elif tool == "Bash":
        segs = search_segments(inp.get("command", ""))
        if not segs:
            return 0
        pattern = bash_pattern(inp.get("command", ""))
        candidates = [d for s in segs for d in bash_dirs(s, cwd)] + bash_dirs(inp.get("command", ""), cwd)[:1]
    else:
        return 0
    repo = next((r for r in map(served_repo, candidates) if r), None)
    if repo is None or not first_copy(ev):
        return 0
    try:
        out = answer_or_record(ev, repo, tool, inp, pattern)
    except Exception:  # noqa: BLE001  devkb must never get in the search's way
        out = None
    if out:
        print(json.dumps(out))
        return 0
    if not first_of_session(ev):
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
