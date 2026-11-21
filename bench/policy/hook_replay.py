#!/usr/bin/env python3
"""Replay archived runs' searches through a guardrail (#367): what would this guardrail have answered?

Every Grep, Bash and Read call of a run's `stream.jsonl` (the hook's matcher) goes to the guardrail as the PreToolUse
event Claude Code would have sent: in the run's order, with the run's session id and a HOME of its own per stream, the
run's checkout path (also as `~/...`) rewritten to the replay's checkout, and the working directory a `cd` left for the
next calls. The checkout should be the run's base with its graph built. A call the guardrail logs a line for is a
decision; any other call (a test run, an edit) is skipped, as the hook skips it. For each decision, one JSON line:

  run, i (the call's position), tool, search, action, reason, intent, names, verdicts,
  reminded   the session's one reminder came with the call
  delivered  the decision's text reached the agent (emit() marks the decision's log line); an answer built and then
             lost (an exception after logging, #393) is not delivered, even when the reminder was printed instead
  chars      characters of the delivered answer (0 when not delivered); printed: characters the hook printed
  ms, timed_out   the hook's run time; the live limit is 20 s
  after_edit the run had changed a file before this call, so the base no longer holds the code the live hook saw
  live_chars what the run's own hook gave for the call, from a stream recorded with --include-hook-events
             (0 for the reminder; null when the stream has no hook events)
  next       the agent's next call in the run

then a summary line: decisions, answers (delivered), the answer rate, characters per answer, agreement with the live
hook where it was recorded, the counts before the first edit, and the counts per action, reason and intent.

  python bench/policy/hook_replay.py --repo CHECKOUT [--guard scripts/devkb_guardrail.py] [--code DEVKB_CODE] \
      RUN_DIR_OR_STREAM ...

`--guard` is the guardrail script to replay. It imports devkb from its own checkout first; `--code` (PYTHONPATH) is
the devkb it runs only when the script is not in a checkout (`git show <sha>:scripts/devkb_guardrail.py > g.py`), and
the replay refuses to start when neither holds a devkb package. Nothing is sent to a model: the agent's next call is
the one it made in the run, whatever the answer would have changed.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ANSWERS = ("substitute", "read-answer", "alongside", "teach", "span-hint")   # actions that give the agent devkb's text
TIMEOUT = 20                                                        # seconds, as the live hook (.claude/settings.json)


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


REMINDER = "devkb guardrail: this is a code search"   # the start of the session's one reminder, not an answer


def hook_text(stdout: str) -> str:
    """What a PreToolUse hook gave the agent: the reason that replaces the call, or the context beside it."""
    try:
        h = json.loads(stdout).get("hookSpecificOutput", {}) if stdout.strip() else {}
    except ValueError:
        return ""
    return h.get("permissionDecisionReason") or h.get("additionalContext") or ""


def live_outputs(stream: Path) -> tuple[dict[str, str], set[str]]:
    """({tool call id: the text the run's own PreToolUse hook gave for it}, {ids of calls the session refused}), from a
    stream recorded with `--include-hook-events`. A hook response names its tool (`PreToolUse:Grep`), and calls can
    overlap (a Read and a Grep sent together), so each response goes to the oldest call of that tool still waiting for
    one. Both are empty for an older stream, apart from the refusals."""
    out, refused, pending = {}, set(), []
    for line in stream.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            pending += [(b.get("id"), b.get("name")) for b in e.get("message", {}).get("content", []) or []
                        if b.get("type") == "tool_use"]
        elif e.get("type") == "user":
            for b in (e.get("message", {}).get("content") or []) if isinstance(e.get("message", {}).get("content"), list) else []:
                if b.get("type") == "tool_result" and b.get("is_error"):
                    text = b.get("content") if isinstance(b.get("content"), str) else json.dumps(b.get("content"))
                    if re.search(r"(?i)require[sd]? approval|approve only if|permission|was denied", text or ""):
                        refused.add(b.get("tool_use_id"))
        elif e.get("type") == "system" and e.get("subtype") == "hook_response" and e.get("hook_event") == "PreToolUse":
            tool = (e.get("hook_name") or "").partition(":")[2]
            k = next((j for j, (_, n) in enumerate(pending) if n == tool or not tool), None)
            if k is not None:
                cid, _ = pending.pop(k)
                out[cid] = hook_text(e.get("stdout") or e.get("output") or "")
    return out, refused


def rewrite(value, old: str, new: str):
    """The call's input with the run's checkout path replaced by the replay's checkout."""
    if not old:
        return value
    text = json.dumps(value)
    home = str(Path.home())
    olds = [old] + (["~" + old[len(home):]] if old.startswith(home + "/") else [])   # `cd ~/...` too
    for o in olds:
        text = text.replace(json.dumps(o)[1:-1], json.dumps(new)[1:-1])
    return json.loads(text)


def search_text(call: dict) -> str:
    inp = call["input"]
    return inp.get("pattern", "") if call["name"] == "Grep" else inp.get("command", "")


EDITS = re.compile(r"(^|[;&|]\s*)(sed\s+-i|tee\s|cp\s|mv\s|rm\s)|open\([^)]*,\s*['\"][wa]|\.write_text\(")
REDIRECT = re.compile(r"(?<![<>&\d])>>?(?!&)\s*(\S+)")


def edits(call: dict) -> bool:
    """Whether a call changes the checkout: Edit/Write, or a shell command that writes a file of it (`sed -i`, a write
    from Python, a redirect into a checkout file). A redirect to /dev/null or a scratch file outside, or a `>` inside a
    quoted pattern, is not one. From then on the run's files differ from the base the replay searches, so its later
    decisions are a different situation (`after_edit`)."""
    if call["name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return True
    if call["name"] != "Bash":
        return False
    cmd = call["input"].get("command", "")
    head = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "<<H", cmd, flags=re.S)      # a heredoc's text is not the command
    unquoted = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", head)
    targets = [t for t in REDIRECT.findall(unquoted) if not t.startswith(("/dev/", "/tmp/"))]
    return bool(targets) or bool(EDITS.search(cmd))


CD = re.compile(r"^\s*cd\s+(\S+)\s*(?:$|&&|;)")


def short(call: dict | None) -> str:
    if call is None:
        return "(end of run)"
    inp = call["input"]
    what = inp.get("command") or inp.get("pattern") or inp.get("file_path") or ""
    return f"{call['name']}: {str(what)[:120]}"


def replay_stream(stream: Path, repo: Path, guard: Path, code: Path) -> list[dict]:
    orig, session, calls = tool_calls(stream)
    live, refused = live_outputs(stream)
    run = stream.parent.name
    out = []
    with tempfile.TemporaryDirectory() as home:
        log = Path(home) / ".claude" / "hooks" / "devkb-guardrail.log"
        env = dict(os.environ, HOME=home, CLAUDE_PROJECT_DIR=str(repo), DEVKB_MISSLOG="0", DEVKB_TELEMETRY="0",
                   PYTHONPATH=os.pathsep.join(filter(None, [str(code), os.environ.get("PYTHONPATH", "")])))
        env.pop("DEVKB_GUARDRAIL", None)
        edited, cwd, decided = False, repo, set()
        for i, call in enumerate(calls):
            after_edit = edited
            edited = edited or (call["id"] not in refused and edits(call))     # a refused command changed nothing
            if call["name"] not in ("Grep", "Bash", "Read"):    # the hook's matcher (.claude/settings.json)
                continue
            inp = rewrite(call["input"], orig, str(repo))
            ev = {"session_id": session or run, "hook_event_name": "PreToolUse", "tool_name": call["name"],
                  "tool_input": inp, "tool_use_id": call["id"], "cwd": str(cwd)}
            m = CD.match(inp.get("command", "")) if call["name"] == "Bash" and call["id"] not in refused else None
            if m:                                         # the Bash tool keeps a `cd` for the session's next calls
                d = (cwd / m.group(1)).resolve() if not m.group(1).startswith("/") else Path(m.group(1)).resolve()
                cwd = d if d.is_dir() and d.is_relative_to(repo) else cwd
            before = len(log.read_text().splitlines()) if log.exists() else 0
            t0 = time.monotonic()
            try:                                          # the live hook's limit (.claude/settings.json: 20 s)
                p = subprocess.run([sys.executable, "-P", str(guard)], input=json.dumps(ev), env=env, cwd=repo,
                                   capture_output=True, text=True, timeout=TIMEOUT)
                stdout, timed_out = p.stdout, False
            except subprocess.TimeoutExpired:
                stdout, timed_out = "", True              # Claude Code drops a hook that runs over its limit
            ms = int((time.monotonic() - t0) * 1000)
            new = log.read_text().splitlines()[before:] if log.exists() else []
            if not new:
                continue                                  # not a call the guardrail decides on
            rows = [json.loads(x) for x in new if x.strip()]
            # a call can log two lines: its decision, then the session's one reminder; the decision is the call's
            last = next((r for r in rows if r.get("action") != "remind"), rows[-1])
            reminded = any(r.get("action") == "remind" for r in rows)
            # delivered: emit() marks the decision line with what it gave; a decision whose answer was built and then
            # lost (an exception after logging, #393) has no mark, even when the reminder was printed in its place
            delivered = last.get("action") != "remind" and "answer_sha1" in last and not timed_out
            text = hook_text(stdout)
            lv = live.get(call["id"]) if live else None
            decided.add(call["id"])
            out.append({"run": run, "i": i, "tool": call["name"], "search": search_text(call)[:200],
                        "action": last.get("action", ""), "reason": last.get("reason", ""), "intent": last.get("intent", ""),
                        "names": last.get("names", []), "verdicts": last.get("verdicts", []), "reminded": reminded,
                        "delivered": delivered, "chars": last.get("answer_chars", len(text)) if delivered else 0,
                        "printed": len(text), "printed_reminder": text.startswith(REMINDER),
                        "ms": ms, "timed_out": timed_out, "after_edit": after_edit, "refused": call["id"] in refused,
                        "live_chars": None if lv is None else (0 if lv.startswith(REMINDER) else len(lv)),
                        "next": short(calls[i + 1] if i + 1 < len(calls) else None)})
    for cid, text in live.items():                        # the live hook answered a call the replay did not decide on
        if text and not text.startswith(REMINDER) and cid not in decided:
            out.append({"run": run, "i": next(i for i, c in enumerate(calls) if c["id"] == cid), "tool": "", "search": "",
                        "action": "(no decision)", "reason": "", "intent": "", "names": [], "verdicts": [],
                        "reminded": False, "delivered": False, "chars": 0, "printed": 0, "printed_reminder": False,
                        "ms": 0, "timed_out": False, "after_edit": False, "refused": cid in refused,
                        "live_chars": len(text), "next": "", "undecided": True})
    return out


def summary(rows: list[dict]) -> dict:
    """Counts over the decisions. An answer is a decision whose text reached the agent (`delivered`), whatever its
    action; `live_answers` counts the same from the run's own hook output, where the stream recorded it."""
    undecided = [r for r in rows if r.get("undecided")]
    rows = [r for r in rows if not r.get("undecided")]
    answers = [r for r in rows if r["delivered"]]
    chars = [r["chars"] for r in answers]
    live = [r for r in rows if r["live_chars"] is not None]
    return {"decisions": len(rows), "answers": len(answers),
            "live_recorded": len(live), "live_answers": sum(1 for r in live if r["live_chars"]),
            "agree_with_live": sum(1 for r in live if bool(r["live_chars"]) == r["delivered"]),
            "live_answers_without_a_decision": len(undecided),          # disagreements too
            "timed_out": sum(r["timed_out"] for r in rows), "ms_max": max((r["ms"] for r in rows), default=0),
            "before_first_edit": sum(not r["after_edit"] for r in rows),
            "answers_before_first_edit": sum(r["delivered"] and not r["after_edit"] for r in rows),
            "answer_rate": round(len(answers) / len(rows), 3) if rows else 0.0,
            "chars_median": statistics.median(chars) if chars else 0, "chars_max": max(chars, default=0),
            "reminders": sum(r["reminded"] for r in rows),
            "actions": dict(collections.Counter(r["action"] for r in rows)),
            "reasons": dict(collections.Counter(r["reason"] or "-" for r in rows if not r["delivered"])),
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
    guard = Path(a.guard).resolve()
    if not (guard.parents[1] / "devkb").is_dir() and not (Path(a.code) / "devkb").is_dir():
        # the guardrail imports devkb from its own checkout first (sys.path), then from PYTHONPATH (--code)
        ap.error(f"{guard} is not in a devkb checkout and --code {a.code} holds no devkb package")
    rows = []
    for s in streams(a.paths):
        for r in replay_stream(s, Path(a.repo).resolve(), Path(a.guard).resolve(), Path(a.code).resolve()):
            rows.append(r)
            print(json.dumps(r), flush=True)
    print(json.dumps({"summary": summary(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
