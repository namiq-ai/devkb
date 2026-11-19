"""What every devkb call came to (#151): `outcome`, `detail`, `resolved` for each telemetry line, and `devkb stats`,
which counts them by tool and outcome (and the guardrail's decisions, #149, with `devkb guardrail-stats`)."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

OUTCOMES = ("complete", "incomplete", "ambiguous", "fallback-text", "no-match", "refused", "error")
DETAIL_MAX = 200
_REFUSED = re.compile(r"bad arguments|outside|stale|not built|no graph|must be|give a|give words|unknown (tool|role)", re.I)


def _cut(s: str) -> str:
    return " ".join(str(s).split())[:DETAIL_MAX]


def outcome_of_reply(reply: dict) -> tuple[str, str, str]:
    """(outcome, detail, resolved) for one ProcessAPI reply dict."""
    err = reply.get("error")
    if err:
        err = str(err)
        if reply.get("matches") or reply.get("candidates"):
            return "ambiguous", _cut(err), ""
        if _REFUSED.search(err):
            return "refused", _cut(err), ""
        if "failed" in err:
            return "error", _cut(err), ""
        return "no-match", _cut(err), ""
    ms = reply.get("matches")
    if isinstance(ms, list):
        if not ms:
            return "no-match", "", ""
        if len(ms) > 1 or (reply.get("n") or 0) > 1:
            return "ambiguous", _cut(f"{reply.get('n', len(ms))} matches ({reply.get('how')})"), ""
        m = ms[0]
        return "complete", "", str(m.get("k") or m.get("key") or "") if isinstance(m, dict) else str(m)
    if "n_hits" in reply and not reply["n_hits"]:
        return "no-match", "", ""
    if reply.get("complete") is False:
        return "incomplete", _cut(f"{reply.get('unresolved_calls', '')} unresolved calls".strip()), ""
    return "complete", "", ""


def outcome_of_pack(text: str) -> tuple[str, str, str]:
    """(outcome, detail, resolved) for the text of a pack."""
    from devkb.misses import verdict_of
    if text.startswith("devkb pack:") or text.startswith("Unknown kind"):
        return "refused", _cut(text), ""
    verdict, detail = verdict_of(text)
    m = re.match(r"# Graph pack: [^\n`]*`([^`\n]+)`", text)
    resolved = m.group(1) if m else ""
    if verdict == "cannot-resolve":
        if "It could be:" in text:
            return "ambiguous", _cut(detail), ""
        if "## Text matches (not resolved" in text:
            return "fallback-text", _cut(detail), ""
        return "no-match", _cut(detail), ""
    if verdict == "incomplete":
        return "incomplete", _cut(detail), resolved
    if verdict == "complete":
        return "complete", "", resolved
    lines = text.splitlines()
    if len(lines) > 2 and re.search(r"has no |no [a-z ]+ (in|matches)|cannot", lines[2]) and not resolved:
        return "no-match", _cut(lines[2]), ""
    return "complete", "", resolved


# ── summaries ─────────────────────────────────────────────────────────────────
def _rows(path: Path) -> list[dict]:
    out = []
    try:
        for line in path.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    except OSError:
        pass
    return out


def _table(rows: list[dict], key: str, label: str) -> list[str]:
    by: dict[str, Counter] = {}
    for r in rows:
        by.setdefault(str(r.get(key) or "?"), Counter())[r.get("outcome") or "unrecorded"] += 1
    cols = OUTCOMES + (("unrecorded",) if any("unrecorded" in c for c in by.values()) else ())
    out = [f"{label:<20} {'total':>5} " + " ".join(f"{c:>13}" for c in cols)]
    for k in sorted(by):
        out.append(f"{k:<20} {sum(by[k].values()):>5} " + " ".join(f"{by[k][c]:>13}" for c in cols))
    return out


def render_stats(repo: Path) -> str:
    from devkb.service import TELEMETRY_NAME
    path = repo / ".devkb" / TELEMETRY_NAME
    rows = _rows(path)
    if not rows:
        return f"devkb stats: no calls logged in {path}."
    out = [f"{len(rows)} call(s) in {path}", "", *_table(rows, "tool", "tool")]
    out += ["", "total: " + ", ".join(f"{c} {n}" for c, n in Counter(r.get("outcome") or "unrecorded" for r in rows).most_common())]
    for s in sorted({str(r["session"]) for r in rows if r.get("session")}):
        out += ["", f"session {s}:", *_table([r for r in rows if r.get("session") == s], "tool", "tool")]
    return "\n".join(out)


ACTIONS = ("substitute", "read-answer", "alongside", "span-hint", "remind", "pass-through", "repeat")   # every action (#214)


def guardrail_log() -> Path:
    return Path.home() / ".claude" / "hooks" / "devkb-guardrail.log"


def intents(rows: list[dict]) -> list[str]:
    """Intents by action (#214): which questions the searches asked, and what the hook did with each."""
    c = Counter((r.get("intent") or "unrecorded", r["action"]) for r in rows)
    kinds = sorted({i for i, _ in c}, key=lambda i: -sum(n for (j, _a), n in c.items() if j == i))
    acts = [a for a in ACTIONS if any(a == b for _i, b in c)]
    lines = ["intent by action:", "| intent | " + " | ".join(acts) + " |", "|---|" + "---|" * len(acts)]
    lines += [f"| {i} | " + " | ".join(str(c[(i, a)]) for a in acts) + " |" for i in kinds]
    return lines


def render_guardrail(log: Path | None = None, repo: str = "") -> str:
    log = log or guardrail_log()
    rows = [r for r in _rows(log) if r.get("action") and (not repo or r.get("repo") == repo)]
    if not rows:
        return f"devkb guardrail-stats: no guardrail decisions logged in {log}."

    def block(rs: list[dict]) -> list[str]:
        c = Counter(r["action"] for r in rs)
        pt = Counter(v for r in rs if r["action"] == "pass-through" for v in (r.get("verdicts") or ["none"]))
        lines = [", ".join(f"{a} {c[a]}" for a in ACTIONS)]
        if pt:
            lines.append("  pass-through by verdict: " + ", ".join(f"{v} {n}" for v, n in sorted(pt.items())))
        if c["repeat"]:
            lines.append("  repeats suggest the answer was not enough")
        return lines

    out = [f"{len(rows)} guardrail decision(s) in {log}", "", "total:", *block(rows), "", *intents(rows)]
    for s in sorted({str(r.get("session")) for r in rows}):
        out += ["", f"session {s}:", *block([r for r in rows if str(r.get("session")) == s])]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="devkb stats", description="counts of devkb calls by tool and outcome")
    ap.add_argument("--project", default=".")
    ap.add_argument("--guardrail", action="store_true", help="count the guardrail's decisions instead")
    ap.add_argument("--log", default="", help="guardrail log (default ~/.claude/hooks/devkb-guardrail.log)")
    a = ap.parse_args(argv)
    if a.guardrail:
        print(render_guardrail(Path(a.log) if a.log else None))
    else:
        print(render_stats(Path(a.project).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
