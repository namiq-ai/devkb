"""Requirement + Evidence, CHILD_OF / DERIVED_FROM / IMPLEMENTS / EVIDENCED_BY
(devkb BL-14, ADR-SDP-DEVKB-002, ODSF-230).

Links the renovated lifecycle into the graph, so "which stories implement this
spec" and "what evidence supports this" are graph questions:

- **Evidence** nodes from every evidence pack under `.onboarding/evidence/<EVP>/`:
  one per `ev_` record in `manifest.json` `evidence[]` (REA's ids -- ODSF never
  computes one) and one per `of_` record in `odsf-findings.jsonl`. `confidence`
  is copied exactly as recorded and never upgraded. Only ids, confidence and a
  short label land here: the pack is the record, not the graph (ADR §Consequences).
- a ticket's `## Trace` rows: `Requirement` -> a `Requirement` node + `DERIVED_FROM`;
  `Epic` -> `CHILD_OF` (a STORY to an EPIC only); `Specification` -> `IMPLEMENTS`, resolved to a Spec node
  by its path or its `spec_id`.
- an `ev_`/`of_` id named in a ticket or a Spec file -> `EVIDENCED_BY`.

Every edge is added only when both ends exist in the graph. A reference that
cannot be resolved is reported on stderr at build and never guessed -- the same
rule as `DOCUMENTS`. Deterministic and regex-derived, no LLM call. Post-merge:
needs the merged graph's Ticket nodes and `spec_docs`' Spec nodes, so it runs
after both (`devkb/build.py`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from devkb.extractors.tickets_git import _iter_ticket_files, _parse_metadata
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

EVIDENCE_DIR = Path(".onboarding") / "evidence"

_EV_ID_RE = re.compile(r"^ev_[0-9a-f]{64}$")
_OF_ID_RE = re.compile(r"^of_[0-9a-f]{64}$")
_CITED_ID_RE = re.compile(r"(?<![0-9A-Za-z_])(?:ev|of)_[0-9a-f]{64}(?![0-9A-Za-z_])")
_REQ_RE = re.compile(r"\bREQ-\d+\b")
_TRACE_HEADER_RE = re.compile(r"^##\s+Trace\s*$", re.MULTILINE)
_NEXT_SECTION_RE = re.compile(r"^##\s", re.MULTILINE)
_TRACE_ROW_RE = re.compile(r"^\|\s*(Requirement|Specification|Epic)\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
# A Trace row nobody has filled in yet says so; that is not an unresolved reference.
_PLACEHOLDERS = frozenset({"", "-", "—", "–", "tbd", "n/a", "na", "none"})
_LABEL_MAX = 120


def _trace_rows(text: str) -> list[tuple[str, str]]:
    """`(link, value)` for the Requirement/Specification/Epic rows of `## Trace`."""
    m = _TRACE_HEADER_RE.search(text)
    if not m:
        return []
    rest = text[m.end():]
    nxt = _NEXT_SECTION_RE.search(rest)
    section = rest[:nxt.start()] if nxt else rest
    return [(link, value) for link, value in _TRACE_ROW_RE.findall(section)]


def _label(*parts: Any) -> str:
    text = " ".join(str(p) for p in parts if p)
    return text[:_LABEL_MAX]


def _subject(rec: dict[str, Any]) -> dict[str, Any]:
    subject = rec.get("subject")
    return subject if isinstance(subject, dict) else {}


def _read_pack(pack_dir: Path) -> tuple[str, list[dict[str, str]]] | str:
    """`(pack_id, records)` for a well-formed pack, else the reason it is not.

    All-or-nothing: one malformed record skips the whole pack, so a pack never
    lands half-indexed and looking complete."""
    try:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"manifest.json unreadable ({exc.__class__.__name__})"
    if not isinstance(manifest, dict) or not isinstance(manifest.get("evidence", []), list):
        return "manifest.json is not a pack manifest"
    pack_id = manifest.get("id")
    if not isinstance(pack_id, str) or not pack_id:
        return "manifest.json has no id"

    records: list[dict[str, str]] = []
    for i, rec in enumerate(manifest.get("evidence", [])):
        if not isinstance(rec, dict) or not _EV_ID_RE.match(str(rec.get("evidence_id", ""))) \
                or not isinstance(rec.get("confidence"), str):
            return f"manifest.json evidence[{i}] has no valid ev_ id and confidence"
        subject = _subject(rec)
        records.append({
            "id": rec["evidence_id"], "origin": "rea", "confidence": rec["confidence"],
            "label": _label(rec.get("operation"), subject.get("alias") or subject.get("name")),
        })

    findings = pack_dir / "odsf-findings.jsonl"
    if findings.exists():
        try:
            lines = findings.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return f"odsf-findings.jsonl unreadable ({exc.__class__.__name__})"
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                return f"odsf-findings.jsonl line {n} is not JSON"
            if not isinstance(rec, dict) or not _OF_ID_RE.match(str(rec.get("id", ""))) \
                    or not isinstance(rec.get("confidence"), str):
                return f"odsf-findings.jsonl line {n} has no valid of_ id and confidence"
            subject = _subject(rec)
            records.append({
                "id": rec["id"], "origin": "odsf", "confidence": rec["confidence"],
                "label": _label(rec.get("kind"), subject.get("name") or subject.get("local_path")),
            })
    return pack_id, records


def _add_evidence(ctx: ProjectContext, g: DevKBGraph, report: list[str]) -> set[str]:
    root = ctx.repo_root / EVIDENCE_DIR
    known: dict[str, str] = {}  # id -> confidence as first recorded
    if not root.is_dir():
        return set()
    for pack_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        rel = str(pack_dir.relative_to(ctx.repo_root))
        result = _read_pack(pack_dir)
        if isinstance(result, str):
            report.append(f"{rel}: evidence pack skipped -- {result}")
            continue
        pack_id, records = result
        for rec in records:
            if rec["id"] in known:
                # first pack (sorted) to record an id owns it; never re-labelled
                if known[rec["id"]] != rec["confidence"]:
                    report.append(f"{rel}: {rec['id'][:15]}… recorded as {rec['confidence']!r}, already "
                                  f"{known[rec['id']]!r} in an earlier pack -- earlier record kept")
                continue
            known[rec["id"]] = rec["confidence"]
            g.add_node(
                "Evidence", rec["id"], source="evidence-pack",
                confidence=rec["confidence"], origin=rec["origin"],
                pack=pack_id, pack_dir=rel, label=rec["label"] or rec["id"][:15],
            )
    return set(known)


def _spec_lookup(graph: DevKBGraph) -> tuple[set[str], dict[str, list[str]]]:
    paths: set[str] = set()
    by_id: dict[str, list[str]] = {}
    for spec in graph.nodes("Spec"):
        paths.add(spec.natural_key)
        spec_id = spec.props.get("spec_id")
        if spec_id:
            by_id.setdefault(spec_id, []).append(spec.natural_key)
    return paths, {k: sorted(v) for k, v in by_id.items()}


def _resolve_specs(value: str, paths: set[str], by_id: dict[str, list[str]],
                   where: str, report: list[str]) -> list[str]:
    out: list[str] = []
    for token in re.split(r"[,\s]+", value.replace("`", "")):
        if token.lower() in _PLACEHOLDERS:
            continue
        if token in paths:
            out.append(token)
            continue
        matches = by_id.get(token, [])
        if len(matches) == 1:
            out.append(matches[0])
        elif matches:
            report.append(f"{where}: Specification {token} is ambiguous ({', '.join(matches)}) -- not linked")
        else:
            report.append(f"{where}: Specification {token} is not a Spec in the graph -- not linked")
    return out


def _cite_evidence(g: DevKBGraph, src_type: str, src: str, text: str, where: str,
                   known: set[str], report: list[str]) -> None:
    for ev_id in sorted(set(_CITED_ID_RE.findall(text))):
        if ev_id not in known:
            report.append(f"{where}: cites {ev_id[:15]}… which is in no evidence pack -- not linked")
            continue
        g.add_edge(
            "EVIDENCED_BY", src_type, src, "Evidence", ev_id,
            source="evidence-cite", confidence=1.0, evidence_ref=f"{where} cites {ev_id}",
        )


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    g = DevKBGraph()
    report: list[str] = []
    real_tickets = {t.natural_key: t.props.get("ticket_type") for t in graph.nodes("Ticket")}
    epic_re = re.compile(rf"\b{re.escape(ctx.ticket_prefix)}-\d+\b")
    known_evidence = _add_evidence(ctx, g, report)
    spec_paths, spec_by_id = _spec_lookup(graph)

    for path in _iter_ticket_files(ctx):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        ticket = _parse_metadata(text, path)["ticket"]
        if ticket not in real_tickets:
            continue
        where = str(path.relative_to(ctx.repo_root))
        trace_ref = f"{where}#Trace"

        for link, value in _trace_rows(text):
            if value.strip().lower() in _PLACEHOLDERS:
                continue
            if link == "Requirement":
                reqs = _REQ_RE.findall(value)
                if not reqs:
                    report.append(f"{where}: Requirement {value!r} names no REQ-NNN -- not linked")
                for req in reqs:
                    g.add_node("Requirement", req, source="ticket-trace")
                    g.add_edge("DERIVED_FROM", "Ticket", ticket, "Requirement", req,
                               source="ticket-trace", confidence=1.0, evidence_ref=trace_ref)
            elif link == "Epic":
                epics = epic_re.findall(value)
                if not epics:
                    report.append(f"{where}: Epic {value!r} names no {ctx.ticket_prefix}-NNN -- not linked")
                for epic in epics:
                    if epic == ticket:
                        report.append(f"{where}: Epic {epic} is the ticket itself -- not linked")
                        continue
                    if epic not in real_tickets:
                        report.append(f"{where}: Epic {epic} is not a Ticket in the graph -- not linked")
                        continue
                    # ADR-SDP-DEVKB-002 §3: CHILD_OF is Story -> Epic, nothing else.
                    if real_tickets[ticket] != "STORY" or real_tickets[epic] != "EPIC":
                        report.append(f"{where}: Epic row links {real_tickets[ticket]} {ticket} to "
                                      f"{real_tickets[epic]} {epic}; CHILD_OF is STORY -> EPIC -- not linked")
                        continue
                    g.add_edge("CHILD_OF", "Ticket", ticket, "Ticket", epic,
                               source="ticket-trace", confidence=1.0, evidence_ref=trace_ref)
            else:  # Specification
                for spec in _resolve_specs(value, spec_paths, spec_by_id, where, report):
                    g.add_edge("IMPLEMENTS", "Ticket", ticket, "Spec", spec,
                               source="ticket-trace", confidence=1.0, evidence_ref=trace_ref)

        _cite_evidence(g, "Ticket", ticket, text, where, known_evidence, report)

    for spec_path in sorted(spec_paths):
        try:
            text = (ctx.repo_root / spec_path).read_text(errors="replace")
        except OSError:
            continue
        _cite_evidence(g, "Spec", spec_path, text, spec_path, known_evidence, report)

    if report:
        lines = sorted(set(report))
        print(f"devkb build: lifecycle: {len(lines)} unresolved reference(s), none guessed:",
              file=sys.stderr)
        for line in lines:
            print(f"  {line}", file=sys.stderr)
    return g
