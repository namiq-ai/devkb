"""What a benchmark run did, read from its `claude -p --output-format stream-json --verbose` stream (#447).

Pure functions: a stream file in, a flat record out. Nothing here runs an agent or a graph tool.

Counted, per run:
  tokens     input, output, cache creation, cache read. The run's totals come from the final `result` event (`tokens`); the per-message usage in the
             stream is kept only as `tokens_by_message`: its output_tokens are placeholders written before the message finishes (1,101 against
             16,274 on a recorded run), so it must not be reported
  turns      distinct assistant messages; `num_turns` from the result event
  tools      calls by tool name and by kind (grep, find, readcmd, git, build_test, devkb, cbm_cli, Read, Edit, ...), navigation versus verification
  results    size in characters of every tool result, by kind: what each tool put in the model's context
  graph      every call to a graph tool (an `mcp__devkb*` / `mcp__codebase*` tool, or `devkb` / `codebase-memory-mcp` through the shell) with its
             outcome: answered, empty, partial, error, refused; whether a search followed within 2 calls; whether a later call touched a file it named
  hooks      hook starts and responses by event, and how many put text into the model's context
"""
from __future__ import annotations

import json
import re
from pathlib import Path

GRAPH_MCP = re.compile(r"^mcp__(devkb|codebase[-_]memory)")
SHELL_KINDS = [  # first match wins; applied to each command segment of a pipeline or `&&` chain
    ("cbm_cli", re.compile(r"(^|/)codebase-memory-mcp\b")),
    ("devkb", re.compile(r"(^|/)devkb\b")),
    ("grep", re.compile(r"^(grep|egrep|fgrep|rg|ag|ack)\b")),
    ("find", re.compile(r"^(find|fd|ls|tree|locate)\b")),
    ("readcmd", re.compile(r"^(cat|head|tail|sed|awk|less|more|nl|wc|xxd|od)\b")),
    ("git", re.compile(r"^git\b")),
    ("build_test", re.compile(r"(^|/)(ninja|cmake|make|west|twister|pytest|python3? -m pytest|zephyr\.exe)\b|\.exe\b")),
]
NAVIGATION = {"grep", "find", "readcmd", "Read", "Grep", "Glob", "graph"}
SEARCH = {"grep", "find", "Grep", "Glob"}
EMPTY = re.compile(r'(?i)^\s*$|\bno (results|matches|symbols?|projects?|callers|files)\b|"(results|matches|total)":\s*(\[\]|0)\b|\b0 (results|matches)\b|not found')
PARTIAL = re.compile(r"(?i)\*\*incomplete|coverage: incomplete|\btruncated\b|\bpartial\b|\(cut\)|has_more:\s*true")
REFUSED = re.compile(r"(?i)permission (to use|denied)|requires approval|was blocked|not allowed")
PATH = re.compile(r"[\w./+-]+\.(?:c|h|cc|cpp|hpp|py|rst|yaml|yml|txt|inc|S|dts|dtsi|overlay|conf|Kconfig\w*)\b")


def shell_kind(command: str) -> str:
    segments = [s.strip() for s in re.split(r"&&|\|\||;|\|", command or "") if s.strip()]
    for seg in segments:
        seg = re.sub(r"^(cd\s+\S+|export\s+\S+|env\s+(\S+=\S+\s+)*|time\s+|timeout\s+\d+\s+)\s*", "", seg)
        for kind, rx in SHELL_KINDS:
            if rx.search(seg):
                return kind
    return "other"


def tool_kind(name: str, inp: dict) -> str:
    if GRAPH_MCP.match(name):
        return "graph"
    if name == "Bash":
        k = shell_kind(inp.get("command", ""))
        return "graph" if k in ("devkb", "cbm_cli") else k
    return name


def result_text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def outcome(text: str, is_error: bool, denied: bool) -> str:
    if denied or (is_error and REFUSED.search(text)):
        return "refused"
    if is_error:
        return "error"
    if EMPTY.search(text[:400]) and len(text) < 400:
        return "empty"
    if PARTIAL.search(text):
        return "partial"
    return "answered"


def hook_context(stdout: str) -> str:
    """The text a hook put in front of the model: `additionalContext` or `systemMessage` of its JSON output (anything else on stdout as it is)."""
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("level="):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        out.append((d.get("hookSpecificOutput") or {}).get("additionalContext") or "")
        out.append(d.get("systemMessage") or "")
    return "\n".join(x for x in out if x)


def read(stream: Path) -> list[dict]:
    out = []
    for line in Path(stream).read_text(errors="replace").splitlines():
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def parse(stream: Path) -> dict:
    events = read(stream)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    tools_listed = list(init.get("tools") or [])
    usage_by_msg: dict[str, dict] = {}
    calls: list[dict] = []                        # tool_use blocks in order
    by_id: dict[str, dict] = {}
    denied_ids: set[str] = set()
    hooks: dict[str, dict] = {}
    result = {}
    msg_ids: list[str] = []
    for e in events:
        t = e.get("type")
        if t == "assistant":
            m = e.get("message") or {}
            mid = m.get("id")
            if mid and mid not in msg_ids:
                msg_ids.append(mid)
            u = m.get("usage") or {}
            if mid:
                cur = usage_by_msg.setdefault(mid, {})
                for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                    cur[k] = max(cur.get(k, 0), u.get(k, 0) or 0)
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    c = {"id": b["id"], "name": b["name"], "input": inp, "kind": tool_kind(b["name"], inp), "turn": len(msg_ids),
                         "result_chars": None, "is_error": False, "text": ""}
                    calls.append(c)
                    by_id[b["id"]] = c
        elif t == "user":
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in by_id:
                    c = by_id[b["tool_use_id"]]
                    c["text"] = result_text(b.get("content"))
                    c["result_chars"] = len(c["text"])
                    c["is_error"] = bool(b.get("is_error"))
        elif t == "system" and e.get("subtype") == "permission_denied":
            for k in ("tool_use_id", "id"):
                if e.get(k):
                    denied_ids.add(e[k])
        elif t == "system" and e.get("subtype") in ("hook_started", "hook_response"):
            ev = e.get("hook_event") or e.get("hook_name") or "?"
            h = hooks.setdefault(ev, {"started": 0, "responses": 0, "with_text": 0, "chars": 0})
            if e["subtype"] == "hook_started":
                h["started"] += 1
            else:
                h["responses"] += 1
                # only stdout reaches the model, and only as `additionalContext` or `systemMessage`; stderr (cbm's daemon warnings) is noise
                text = hook_context(e.get("stdout") or "")
                if text.strip():
                    h["with_text"] += 1
                    h["chars"] += len(text)
        elif t == "result":
            result = e
    tok = {k: sum(u.get(k, 0) for u in usage_by_msg.values()) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    ru = result.get("usage") or {}
    final = {k: ru.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    by_name: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    chars_by_kind: dict[str, int] = {}
    for c in calls:
        by_name[c["name"]] = by_name.get(c["name"], 0) + 1
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
        chars_by_kind[c["kind"]] = chars_by_kind.get(c["kind"], 0) + (c["result_chars"] or 0)
    graph = []
    for i, c in enumerate(calls):
        if c["kind"] != "graph":
            continue
        nxt = [x["kind"] for x in calls[i + 1:i + 3]]
        named = {Path(p).name for p in PATH.findall(c["text"])}
        later = " ".join(json.dumps(x["input"]) for x in calls[i + 1:] if x["name"] in ("Read", "Edit", "Write", "MultiEdit", "Bash"))
        graph.append({"name": c["name"] if c["name"] != "Bash" else "Bash:" + shell_kind(c["input"].get("command", "")),
                      "turn": c["turn"], "outcome": outcome(c["text"], c["is_error"], c["id"] in denied_ids),
                      "result_chars": c["result_chars"], "search_followed": any(k in SEARCH for k in nxt),
                      "used": bool(named) and any(n in later for n in named)})
    first_graph = next((i for i, c in enumerate(calls) if c["kind"] == "graph"), None)
    nav = [c for c in calls if c["kind"] in NAVIGATION]
    outcomes: dict[str, int] = {}
    for g in graph:
        outcomes[g["outcome"]] = outcomes.get(g["outcome"], 0) + 1
    mcp_tools = [t for t in tools_listed if t.startswith("mcp__")]
    return {
        "model": next(iter(result.get("modelUsage") or {}), None) or (init.get("model") or ""),
        "tools_listed": len(tools_listed), "mcp_tools_listed": len(mcp_tools),
        "graph_tools_listed": sum(1 for t in mcp_tools if GRAPH_MCP.match(t)),
        "turns": len(msg_ids), "num_turns": result.get("num_turns"),
        "tokens": final if result else tok, "tokens_total": sum((final if result else tok).values()), "tokens_by_message": tok,
        "cost_usd": result.get("total_cost_usd"), "duration_ms": result.get("duration_ms"), "duration_api_ms": result.get("duration_api_ms"),
        "stop": result.get("subtype") or ("none" if not result else ""), "is_error": bool(result.get("is_error")),
        "tool_calls": len(calls), "calls_by_name": by_name, "calls_by_kind": by_kind,
        "navigation_calls": len(nav), "verify_calls": by_kind.get("build_test", 0),
        "result_chars_by_kind": chars_by_kind, "result_chars_total": sum(chars_by_kind.values()),
        "graph_calls": len(graph), "graph_outcomes": outcomes, "graph": graph,
        "graph_used_in_run": bool(graph), "first_graph_turn": calls[first_graph]["turn"] if first_graph is not None else None,
        "navigation_before_first_graph": sum(1 for c in calls[:first_graph] if c["kind"] in NAVIGATION) if first_graph is not None else None,
        "hooks": hooks,
    }
