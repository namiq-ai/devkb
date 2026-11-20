#!/usr/bin/env python3
"""Replay archived runs' searches through a guardrail (#367): what would this guardrail have answered?

Every Grep call and every Bash call of a run's `stream.jsonl` goes to the guardrail as the PreToolUse event Claude
Code would have sent, in the run's order and with the run's session id, against a checkout whose graph was built at
the run's base. The run's own checkout path in the commands is rewritten to that checkout. A call the guardrail
decides on (it writes a line to its log) is a decision; any other call (a `ls`, a test run) is skipped, as the hook
skips it. For each decision it prints one JSON line:

  {"run", "i" (the call's position), "tool", "search" (the pattern or command), "action", "reason", "intent",
   "names", "verdicts", "reminded" (the session's one reminder came with it), "chars" (characters the agent would
   have been given), "next" (the agent's next tool call)}

and then a summary line: decisions, answers (substitute, read-answer, alongside, teach), the answer rate, characters
per answer (median, max), and the counts per action, reason and intent.

  python bench/policy/hook_replay.py --repo CHECKOUT [--guard scripts/devkb_guardrail.py] [--code DEVKB_CODE] \
      RUN_DIR_OR_STREAM ...

`--guard` is the guardrail script to replay (a file from any commit: `git show <sha>:scripts/devkb_guardrail.py`);
`--code` is the devkb code it runs (PYTHONPATH; default: this checkout). Each stream gets its own HOME, so the
guardrail's per-session state (reminders, repeated searches) starts empty as it did in the run. Nothing is sent to a
model: the agent's next call is the one it made in the run, whatever the answer would have changed.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ANSWERS = ("substitute", "read-answer", "alongside", "teach")      # the agent is given devkb's answer


def tool_calls(stream: Path) -> tuple[str, str, list[dict]]:
    """(the run's checkout path, its session id, every tool call in order as {id, name, input})."""
    cwd, session, calls, seen = "", "", [], set()
    for line in stream.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            cwd, session = e.get("cwd", ""), e.get("session_id", "")
        if e.get("type") != "assistant":
            continue
        for b in e.get("message", {}).get("content", []) or []:
            if b.get("type") == "tool_use" and b.get("id") not in seen:
                seen.add(b.get("id"))
                calls.append({"id": b.get("id"), "name": b.get("name", ""), "input": b.get("input") or {}})
    return cwd, session, calls


def rewrite(value, old: str, new: str):
    """The call's input with the run's checkout path replaced by the replay's checkout."""
    if not old:
        return value
    return json.loads(json.dumps(value).replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1]))


def search_text(call: dict) -> str:
    inp = call["input"]
    return inp.get("pattern", "") if call["name"] == "Grep" else inp.get("command", "")


def short(call: dict | None) -> str:
    if call is None:
        return "(end of run)"
    inp = call["input"]
    what = inp.get("command") or inp.get("pattern") or inp.get("file_path") or ""
    return f"{call['name']}: {str(what)[:120]}"


def answer_chars(stdout: str) -> int:
    """Characters of what the guardrail gives the agent: the reason that replaces the search, or the context beside it."""
    try:
        h = json.loads(stdout).get("hookSpecificOutput", {})
    except ValueError:
        return 0
    return len(h.get("permissionDecisionReason") or h.get("additionalContext") or "")


def replay_stream(stream: Path, repo: Path, guard: Path, code: Path) -> list[dict]:
    orig, session, calls = tool_calls(stream)
    run = stream.parent.name
    out = []
    with tempfile.TemporaryDirectory() as home:
        log = Path(home) / ".claude" / "hooks" / "devkb-guardrail.log"
        env = dict(os.environ, HOME=home, CLAUDE_PROJECT_DIR=str(repo), DEVKB_MISSLOG="0", DEVKB_TELEMETRY="0",
                   PYTHONPATH=os.pathsep.join(filter(None, [str(code), os.environ.get("PYTHONPATH", "")])))
        env.pop("DEVKB_GUARDRAIL", None)
        for i, call in enumerate(calls):
            if call["name"] not in ("Grep", "Bash"):
                continue
            ev = {"session_id": session or run, "hook_event_name": "PreToolUse", "tool_name": call["name"],
                  "tool_input": rewrite(call["input"], orig, str(repo)), "tool_use_id": call["id"], "cwd": str(repo)}
            before = len(log.read_text().splitlines()) if log.exists() else 0
            p = subprocess.run([sys.executable, "-P", str(guard)], input=json.dumps(ev), env=env, cwd=repo,
                               capture_output=True, text=True, timeout=300)
            new = log.read_text().splitlines()[before:] if log.exists() else []
            if not new:
                continue                                  # not a search the guardrail decides on
            rows = [json.loads(x) for x in new if x.strip()]
            # a call can log two lines: its decision, then the session's one reminder; the decision is the call's
            last = next((r for r in rows if r.get("action") != "remind"), rows[-1])
            reminded = any(r.get("action") == "remind" for r in rows)
            out.append({"run": run, "i": i, "tool": call["name"], "search": search_text(call)[:200],
                        "action": last.get("action", ""), "reason": last.get("reason", ""), "intent": last.get("intent", ""),
                        "names": last.get("names", []), "verdicts": last.get("verdicts", []), "reminded": reminded,
                        "chars": answer_chars(p.stdout), "next": short(calls[i + 1] if i + 1 < len(calls) else None)})
    return out


def summary(rows: list[dict]) -> dict:
    answers = [r for r in rows if r["action"] in ANSWERS and r["chars"]]
    chars = [r["chars"] for r in answers]
    return {"decisions": len(rows), "answers": len(answers),
            "answer_rate": round(len(answers) / len(rows), 3) if rows else 0.0,
            "chars_median": statistics.median(chars) if chars else 0, "chars_max": max(chars, default=0),
            "reminders": sum(r["reminded"] for r in rows),
            "actions": dict(collections.Counter(r["action"] for r in rows)),
            "reasons": dict(collections.Counter(r["reason"] or "-" for r in rows if r["action"] not in ANSWERS)),
            "intents": dict(collections.Counter(r["intent"] for r in rows))}


def streams(paths: list[str]) -> list[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(p.glob("stream.jsonl")) + sorted(p.glob("*/stream.jsonl"))
        else:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", "--checkout", dest="repo", required=True, help="checkout with a graph built at the runs' base")
    ap.add_argument("--guard", default=str(ROOT / "scripts" / "devkb_guardrail.py"), help="the guardrail script to replay")
    ap.add_argument("--code", default=str(ROOT), help="the devkb code the guardrail runs (PYTHONPATH)")
    ap.add_argument("paths", nargs="+", help="stream.jsonl files, run directories, or directories of run directories")
    a = ap.parse_args(argv)
    rows = []
    for s in streams(a.paths):
        for r in replay_stream(s, Path(a.repo).resolve(), Path(a.guard).resolve(), Path(a.code).resolve()):
            rows.append(r)
            print(json.dumps(r), flush=True)
    print(json.dumps({"summary": summary(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
