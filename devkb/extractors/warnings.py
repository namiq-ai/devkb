"""Compliance-violation extractor (devkb Phase 3, ADR-SDP-DEVKB-001).

Ingests dev_compliance_monitor.py --json-report's already-structured
{rule, severity, detail, evidence} feed as-is -- zero new parsing invented,
per the roadmap's own stated goal. Each registered project carries its own
copy of dev_compliance_monitor.py under sdp/devsecops/compliance/ (its own
ROOT resolves via that copy's own __file__, so subprocess-invoking THAT
project's copy correctly checks THAT project's repo -- confirmed ODSF and
OCO each have a real copy; others have none). A project without the script
gets an empty Warning set, not an error -- same "can't check yet" framing
already used elsewhere in devkb for a missing discovery/graph.json.

Always passes --dry-run: dev_compliance_monitor.py's own main() unconditionally
calls create_issue() for every violation found when NOT in dry-run mode --
devkb's build must never have the side effect of filing real tickets.

Most violations have no parseable source-file reference (DEV-06/09's
evidence is "File: <ticket>.md" pointing at issues/, not source; DEV-01/02/
03/04/07/08/10's evidence is process-level free text -- a SHA, a "Run: make
..." hint, a coverage percentage). FLAGGED_BY is only emitted when a real,
on-disk repo-relative path can be confidently parsed out of `evidence`. The
Warning node itself is always created regardless -- a warning with no file
target is still a real, queryable finding ("list every open warning"), not
silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext, run_repo_scripts

_COMPLIANCE_SCRIPT_REL = "sdp/devsecops/compliance/dev_compliance_monitor.py"
_TIMEOUT_S = 120
# Effectively "all time" -- devkb wants the true current state, not a
# rolling recent window (the script's own --since default is 24h, meant for
# its usual CI/cron usage, not a durable "what's currently flagged" answer).
_SINCE_WINDOW = "3650d"

# DEV-05's own evidence shape: "path:line: text[; path:line: text ...]".
_PATH_LINE_RE = re.compile(r"([\w./-]+):(\d+):")
# DEV-06/DEV-09's own evidence shape: "File: <path>".
_FILE_PREFIX_RE = re.compile(r"^File:\s*(\S+)")


def _run_compliance_scan(ctx: ProjectContext) -> list[dict[str, str]]:
    script = ctx.repo_root / _COMPLIANCE_SCRIPT_REL
    if not script.is_file() or not run_repo_scripts(ctx.repo_root):
        return []
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        try:
            subprocess.run(
                ["python3", str(script), "--check-all", "--since", _SINCE_WINDOW,
                 "--dry-run", "--json-report", str(tmp_path)],
                cwd=str(ctx.repo_root), capture_output=True, text=True, timeout=_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        try:
            data = json.loads(tmp_path.read_text())
        except (OSError, ValueError):
            return []
    finally:
        tmp_path.unlink(missing_ok=True)
    violations = data.get("violations", [])
    return violations if isinstance(violations, list) else []


def _extract_files(evidence: str, repo_root: Path) -> list[str]:
    """Best-effort, conservative: only returns paths that actually exist on
    disk under repo_root -- avoids turning a misparsed "Run: make ..." hint
    into a phantom File node."""
    found: list[str] = []
    for m in _PATH_LINE_RE.finditer(evidence):
        candidate = m.group(1)
        if candidate not in found and (repo_root / candidate).is_file():
            found.append(candidate)
    m = _FILE_PREFIX_RE.match(evidence)
    if m and m.group(1) not in found and (repo_root / m.group(1)).is_file():
        found.append(m.group(1))
    return found


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()
    for v in _run_compliance_scan(ctx):
        rule = v.get("rule", "")
        detail = v.get("detail", "")
        evidence = v.get("evidence", "")
        if not rule:
            continue
        # Natural key: sha256(rule+detail+evidence) -- the ontology's original
        # spec was sha256(rule+evidence) alone, widened here after confirming
        # live that several rules' own `evidence` string is fixed boilerplate
        # (e.g. DEV-07's is always the literal "No ADR issue found in issues/
        # for recent schema change", identical across every DEV-07 hit) while
        # `detail` is what actually varies per violation (the specific file,
        # sha, ticket id). rule+evidence alone would silently collapse two
        # distinct real violations into one Warning node the moment a second
        # one occurred -- confirmed this had not yet happened in any
        # registered project's real data, but was a live landmine, not a
        # hypothetical.
        natural_key = hashlib.sha256(f"{rule}:{detail}:{evidence}".encode()).hexdigest()
        g.add_node(
            "Warning", natural_key, source="dev-compliance-monitor",
            rule=rule, severity=v.get("severity", ""), detail=detail,
            evidence=evidence,
        )
        for path in _extract_files(evidence, ctx.repo_root):
            # File may already exist from Phase 2's TOUCHES extraction --
            # add_node() merges props onto the existing node, doesn't
            # duplicate (DevKBGraph.add_node's own dedup-by-key behavior).
            g.add_node("File", path, source="dev-compliance-monitor")
            g.add_edge(
                "FLAGGED_BY", "File", path, "Warning", natural_key,
                source="dev-compliance-monitor", confidence=1.0,
                evidence_ref=f"{rule}: {evidence[:120]}",
            )
    return g


def _history_path(ctx: ProjectContext) -> Path:
    return ctx.devkb_dir / "warnings-history.jsonl"


def _load_history(history_path: Path) -> list[dict]:  # type: ignore[type-arg]
    if not history_path.exists():
        return []
    out: list[dict] = []  # type: ignore[type-arg]
    for line in history_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a corrupt line doesn't invalidate the rest of the log
    return out


def _append_history(history_path: Path, entry: dict) -> None:  # type: ignore[type-arg]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _scan_time(ctx: ProjectContext) -> str:
    """The time this build's scan stands for: the HEAD commit's time, not the wall clock
    (ODSF-230 / ADR-SDP-DEVKB-002 determinism) — rebuilding an unchanged repo yields the same
    graph. Falls back to the clock only outside a git checkout."""
    import subprocess  # noqa: PLC0415

    try:
        out = subprocess.run(["git", "-C", str(ctx.repo_root), "log", "-1", "--format=%cI"],
                             capture_output=True, text=True, timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired, AttributeError):
        out = ""
    return out or datetime.now(timezone.utc).isoformat()


def apply_lifecycle(ctx: ProjectContext, graph: DevKBGraph) -> None:
    """Adds first_seen/last_seen/resolved_at/status to every Warning node
    the current build knows about, PLUS re-adds a node for any warning that
    is in warnings-history.jsonl but absent from this run (i.e. resolved --
    extract() only ever returns currently-open violations, so a fixed
    warning would otherwise silently vanish from the graph the moment it's
    fixed instead of leaving a "this was open from X to Y" record, the exact
    lifecycle tracking this step exists for).

    Must be called on the final MERGED graph, after every extractor's own
    Warning nodes are already in it -- lifecycle needs the whole picture,
    not one extractor's partial view. Appends this build's own scan to
    warnings-history.jsonl as its last step (side effect, not idempotent to
    call twice per build -- build.py calls it exactly once)."""
    history_path = _history_path(ctx)
    history = _load_history(history_path)
    now_iso = _scan_time(ctx)

    current: list[dict] = [
        {
            "natural_key": n.natural_key, "rule": n.props.get("rule", ""),
            "severity": n.props.get("severity", ""), "detail": n.props.get("detail", ""),
            "evidence": n.props.get("evidence", ""),
        }
        for n in graph.nodes("Warning")
    ]

    scans = [*history, {"scanned_at": now_iso, "violations": current}]

    # "" (not None) marks "still open" -- DevKBGraph.add_node() silently
    # drops any prop whose value is None (so a partial update never clobbers
    # an already-set value on merge), which would make resolved_at vanish
    # from props entirely for every open warning instead of storing "not
    # resolved". An empty string is a real, present, falsy value that
    # survives that filter and still means "no resolution timestamp".
    lifecycle: dict[str, dict] = {}
    last_content: dict[str, dict] = {}
    for scan in scans:
        ts = scan.get("scanned_at", now_iso)
        open_now = {v["natural_key"]: v for v in scan.get("violations", []) if v.get("natural_key")}
        for key, rec in lifecycle.items():
            if rec["resolved_at"] == "" and key not in open_now:
                rec["resolved_at"] = ts
        for key, content in open_now.items():
            last_content[key] = content
            if key not in lifecycle:
                lifecycle[key] = {"first_seen": ts, "last_seen": ts, "resolved_at": ""}
            else:
                lifecycle[key]["last_seen"] = ts
                lifecycle[key]["resolved_at"] = ""  # reopened, if it had been resolved

    for key, rec in lifecycle.items():
        content = last_content[key]
        graph.add_node(
            "Warning", key, source="dev-compliance-monitor",
            rule=content["rule"], severity=content["severity"], detail=content["detail"],
            evidence=content["evidence"],
            first_seen=rec["first_seen"], last_seen=rec["last_seen"], resolved_at=rec["resolved_at"],
            status="open" if rec["resolved_at"] == "" else "resolved",
        )

    _append_history(history_path, {"scanned_at": now_iso, "violations": current})
