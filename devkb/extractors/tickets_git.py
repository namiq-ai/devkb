"""Ticket + Bug Lineage + git commit log extractor (devkb Phase 1).

Ports an earlier traceability script's parsing logic
(_parse_metadata, _parse_lineage, _git_commits, _git_files_changed) rather
than rewriting it -- that logic is already correct, proven against OCO's own
large ticket/commit history via `make trace`. The port's job is only to (a)
persist the result instead of re-deriving it every call, and (b) parameterize
the ticket prefix / issues dir / repo root per project instead of hardcoding
OCO's own.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from devkb import github
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

_LINEAGE_VERBS = {
    "caused_by": "CAUSED_BY",
    "regression_of": "REGRESSION_OF",
    "duplicate_of": "DUPLICATE_OF",
    "blocks": "BLOCKS",
}


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=30)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _iter_ticket_files(ctx: ProjectContext) -> list[Path]:
    """Every ticket file for this project: issues_dir plus any
    historical/sprints/*/closed-tickets/ archives -- same two-location search
    traceability.py's _find_issue does per-ticket, generalized to "all"."""
    files: list[Path] = []
    prefix_glob = f"{ctx.ticket_prefix}-*.md"
    if ctx.issues_dir.is_dir():
        files.extend(sorted(ctx.issues_dir.glob(prefix_glob)))
    if ctx.sprint_dir.is_dir():
        for sprint in sorted(ctx.sprint_dir.iterdir()):
            closed = sprint / "closed-tickets"
            if closed.is_dir():
                files.extend(sorted(closed.glob(prefix_glob)))
    return files


def _parse_metadata(text: str, path: Path) -> dict[str, str]:
    stem = path.stem  # PREFIX-NNN_TYPE_PRI_SEV_CREATED_RESOLVED_STATUS_COMPONENT_ASSIGNEE
    parts = stem.split("_")
    fields = ("ticket", "type", "priority", "severity", "created", "resolved", "status",
              "component", "assignee")
    meta = {name: (parts[i] if len(parts) > i else "?") for i, name in enumerate(fields)}
    m = re.search(r"^# .+?: (.+)$", text, re.MULTILINE)
    meta["title"] = m.group(1).strip() if m else "?"
    return meta


def _parse_section(text: str, header: str) -> list[str]:
    pat = rf"^{re.escape(header)}\s*\n((?:[-*].+\n?)*)"
    m = re.search(pat, text, re.MULTILINE)
    if not m:
        return []
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]


def _parse_lineage(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _parse_section(text, "## Bug Lineage"):
        fm = re.match(r"[-*] \*\*(\w+)\*\*:\s*(.+?)(?:\s+—.*)?$", line)
        if fm:
            fields[fm.group(1)] = fm.group(2).strip()
    return fields


def _git_commits(ticket: str, repo_root: Path) -> list[dict[str, str]]:
    out = _run(["git", "log", "--all", f"--grep={ticket}", "--format=%H|%ad|%an|%s",
                "--date=short"], cwd=repo_root)
    # git's own --grep is an unanchored substring/regex match, so
    # --grep=OCO-461 also matches "OCO-4615", "OCO-4610"-"OCO-4619", etc --
    # confirmed live against this repo's own history: OCO-461 alone pulled in
    # a commit for OCO-4615 that relocated the whole factory/ submodule,
    # spuriously attributing ~20k touched files to OCO-461 once devkb Phase 2
    # (ODSF-032) built TOUCHES edges on top of this ticket's commit list. A
    # \b-anchored post-filter rejects that false match ("461" has a word
    # character immediately after it in "4615", so no boundary there) while
    # still accepting real mentions followed by punctuation/whitespace/EOL.
    pattern = re.compile(rf"\b{re.escape(ticket)}\b")
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4 and pattern.search(parts[3]):
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return commits


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()
    authors = github.settings(ctx.repo_root).authors
    for path in _iter_ticket_files(ctx):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        meta = _parse_metadata(text, path)
        ticket = meta["ticket"]
        if ticket == "?":
            continue

        g.add_node(
            "Ticket", ticket, source="tickets",
            title=meta["title"], type=meta["type"],
            # ADR-SDP-DEVKB-002 §2: the alias source for Epic/Story queries
            # (`Ticket{ticket_type: EPIC|STORY}`), normalised so a lower-case
            # filename type cannot fall out of the alias.
            ticket_type=meta["type"].upper(), priority=meta["priority"],
            severity=meta["severity"], status=meta["status"], component=meta["component"],
            assignee=meta["assignee"], created=meta["created"], resolved=meta["resolved"],
            issue_path=str(path.relative_to(ctx.repo_root)),
        )

        lineage = _parse_lineage(text)
        evidence = f"{path.relative_to(ctx.repo_root)}#Bug-Lineage"
        for field, verb in _LINEAGE_VERBS.items():
            target = lineage.get(field)
            if not target:
                continue
            for target_ticket in re.findall(rf"{re.escape(ctx.ticket_prefix)}-\d+", target):
                g.add_edge(
                    verb, "Ticket", ticket, "Ticket", target_ticket,
                    source="bug-lineage", confidence=1.0, evidence_ref=evidence,
                )

        commits = _git_commits(ticket, ctx.repo_root)
        for c in commits:
            g.add_node(
                "Commit", c["hash"], source="git",
                short_hash=c["hash"][:10], date=c["date"], author=c["author"],
                subject=github.public_subject(c["subject"], authors),
            )
            g.add_edge(
                "REFERENCES", "Commit", c["hash"], "Ticket", ticket,
                source="git-log-grep", confidence=1.0,
                evidence_ref=f"git log --grep={ticket}",
            )
    return g
