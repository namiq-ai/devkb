#!/usr/bin/env python3
"""devkb usage per ticket for one working session (single arm): the tickets' time intervals against devkb's telemetry, the guardrail's decisions and the
session transcript's tool calls (#toolmix classes).

  ticket_usage.py mark start 396          # when work on #396 begins
  ticket_usage.py mark end 396            # when it ends
  ticket_usage.py report [--session ID]   # one row per ticket interval

Marks are appended to .devkb/ticket-usage-marks.jsonl (local, untracked). Times are the machine's local time; queries carry no ticket id, so the interval
is the only link, and anything devkb answered in an interval counts for its ticket."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
MARKS = ROOT / ".devkb" / "ticket-usage-marks.jsonl"
GUARD = Path.home() / ".claude" / "hooks" / "devkb-guardrail.log"
TELEMETRY = ROOT / ".devkb" / "process-api-telemetry.jsonl"
PROJECTS = Path.home() / ".claude" / "projects"
ANSWERS = ("alongside", "substitute", "span-hint", "read-answer")


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def mark(kind: str, ticket: str) -> None:
    MARKS.parent.mkdir(exist_ok=True)
    with open(MARKS, "a") as f:
        f.write(json.dumps({"t": now(), "event": kind, "ticket": ticket}) + "\n")


def intervals(marks: list[dict]) -> list[tuple[str, str, str]]:
    """(ticket, start, end) for each start followed by its end; a start with no end runs to now."""
    open_: dict[str, str] = {}
    out = []
    for m in sorted(marks, key=lambda x: x["t"]):
        if m["event"] == "start":
            open_.setdefault(m["ticket"], m["t"])          # a second start of an open ticket continues the span: it does not drop the first
        elif m["ticket"] in open_:
            out.append((m["ticket"], open_.pop(m["ticket"]), m["t"]))
    out += [(t, s, now()) for t, s in open_.items()]
    return sorted(out, key=lambda x: x[1])


def within(t: str, a: str, b: str) -> bool:
    return a <= t < b


def local(ts: str) -> str:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def usage(a: str, b: str, session: str | None, guard=GUARD, telemetry=TELEMETRY, transcript: Path | None = None) -> dict:
    import toolmix as tm
    tel = Counter()
    if telemetry.exists():
        for line in telemetry.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if within(dt.datetime.fromtimestamp(r["t"]).strftime("%Y-%m-%dT%H:%M:%S"), a, b):
                    tel[r["tool"]] += 1
    dec, ans, why = 0, 0, Counter()
    if guard.exists():
        for line in guard.read_text().splitlines():
            if not line.startswith("{"):
                continue
            r = json.loads(line)
            if not r.get("action") or r["action"] == "remind" or not within(r["t"], a, b) or (session and not (r.get("session") or "").startswith(session)):
                continue
            dec += 1
            ans += r["action"] in ANSWERS
            if r["action"] == "pass-through":
                why[r.get("reason")] += 1
    mix = Counter()
    if transcript and transcript.exists():
        for line in transcript.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message")
            c = m.get("content") if isinstance(m, dict) else None
            if d.get("type") != "assistant" or not isinstance(c, list) or not d.get("timestamp") or not within(local(d["timestamp"]), a, b):
                continue
            for blk in c:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    mix["mcp" if blk["name"].startswith("mcp__devkb") else tm.classify(blk["name"], blk.get("input") or {})] += 1
    nav = mix["devkb"] + mix["mcp"] + mix["search"] + mix["read"]
    return {"queries": sum(tel.values()), "by_tool": dict(tel), "decisions": dec, "answered": ans, "stale": why.get("stale-graph", 0), "not_complete": why.get("not-complete", 0),
            "mix": dict(mix), "devkb_share": round((mix["devkb"] + mix["mcp"]) / nav, 3) if nav else None}


def main(a: list[str]) -> int:
    if a[:1] == ["mark"] and len(a) == 3 and a[1] in ("start", "end"):
        mark(a[1], a[2].lstrip("#"))
        return 0
    if a[:1] == ["report"]:
        sid = a[a.index("--session") + 1] if "--session" in a else None
        tr = next(iter(sorted(PROJECTS.glob(f"*{ROOT.name}/{sid or ''}*.jsonl"), key=os.path.getmtime, reverse=True)), None)
        marks = [json.loads(x) for x in MARKS.read_text().splitlines()] if MARKS.exists() else []
        print("| ticket | from | to | devkb queries (tools) | hook decisions | answered | stale | not-complete | session mix | devkb share of navigation |\n|---|---|---|---|---|---|---|---|---|---|")
        for t, s, e in intervals(marks):
            u = usage(s, e, sid, transcript=tr)
            print(f"| #{t} | {s[5:16]} | {e[5:16]} | {u['queries']} {u['by_tool']} | {u['decisions']} | {u['answered']} | {u['stale']} | {u['not_complete']} | {u['mix']} | {u['devkb_share']} |")
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
