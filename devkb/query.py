#!/usr/bin/env python3
"""devkb query — a linked, evidence-backed context bundle for one node.

Usage: python3 devkb/query.py --project CODE --about ODSF-021
       python3 devkb/query.py --project CODE --about M2       (milestone)
       python3 devkb/query.py --project CODE --about A-01     (work package)
       python3 devkb/query.py --project CODE stories implementing SPEC-ODSF-003
                              (also `epics`/`tickets`; a SPEC id or a spec path)

Returns JSON: the node itself plus every edge touching it (outgoing and
incoming), each with the linked node's identifying fields inlined -- a
context bundle an agent or human can act on directly, not a raw file dump
(requirement per ADR-SDP-DEVKB-001 / ODSF-021's acceptance criteria).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.index import DevKBIndex, load
from devkb.model import NODE_TYPES
from devkb.module_file_bridge import file_to_module
from devkb.project_context import resolve, ProjectContext

_STALE_HINT = (
    "no .devkb/ store found for this project -- run "
    "`python3 devkb/build.py --project {code}` first"
)


def _find_node(idx: DevKBIndex, natural_key: str) -> dict[str, Any] | None:
    """Tries every node type for this natural key -- Phase 1 has no path-based
    types yet (File is a later phase), so a plain "what type is this key"
    guess isn't needed: Ticket/Commit ids/WorkPackage ids/Milestone ids don't
    collide in practice, but check all four rather than assuming the caller
    knows the type."""
    for node_type in NODE_TYPES:
        node = idx.node(node_type, natural_key)
        if node is not None:
            return node
    return None


def _linked_summary(node: dict[str, Any]) -> dict[str, Any]:
    props = node.get("properties", {})
    label = props.get("title") or props.get("subject") or node["natural_key"]
    return {"uid": node["uid"], "type": node["type"], "natural_key": node["natural_key"], "label": label}


#: Verbs whose neighbour count is unbounded by construction, and the number of
#: them a bundle carries. `SIMILAR_TO` is threshold-free on purpose — the
#: extractor emits an edge for ANY shared file and stores the real score so
#: that filtering can happen HERE, at query time ("rank at the edge, don't gate
#: at the build"). That half was specified and never built, so a bundle carried
#: every neighbour: measured on OCO, a median ticket had 539 of them and the
#: worst had 1,404, which is not a context bundle, it is the backlog.
_RANKED_VERBS = {"SIMILAR_TO": 10}


def _rank_key(link: dict[str, Any]) -> float:
    ev = link.get("evidence") or {}
    # `weighted_score` knows the difference between sharing a Makefile and
    # sharing one service; `overlap_score` is the pre-BL-11-fix fallback for a
    # graph built before it existed.
    for field in ("weighted_score", "overlap_score", "shared_file_count"):
        value = ev.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _ranked(links: list[dict[str, Any]]) -> dict[str, Any]:
    """Cap the verbs that fan out, and SAY how many were left out.

    Silently dropping links would be the same defect ODSF-058 removed from the
    report — a document that abbreviates without admitting it. The count is
    part of the answer, not an implementation detail.
    """
    omitted: dict[str, int] = {}
    winners: dict[str, list[dict[str, Any]]] = {}
    for verb, cap in _RANKED_VERBS.items():
        group = [link for link in links if link["verb"] == verb]
        if len(group) <= cap:
            continue          # nothing dropped, so nothing reordered either
        group.sort(key=_rank_key, reverse=True)
        omitted[verb] = len(group) - cap
        winners[verb] = group[:cap]

    if not winners:
        return {"links": links, "omitted": omitted}

    # Survivors take the positions the verb already occupied, in rank order:
    # the bundle's overall link order stays the graph's, and a top-N list is
    # returned strongest-first, because for a truncated list the order IS part
    # of the answer.
    queues = {verb: iter(kept) for verb, kept in winners.items()}
    out: list[dict[str, Any]] = []
    for link in links:
        verb = link["verb"]
        if verb not in winners:
            out.append(link)
            continue
        nxt = next(queues[verb], None)
        if nxt is not None:
            out.append(nxt)
    return {"links": out, "omitted": omitted}


def context_bundle(idx: DevKBIndex, natural_key: str, ctx: ProjectContext | None = None) -> dict[str, Any]:
    node = _find_node(idx, natural_key)
    if node is None:
        return {"found": False, "natural_key": natural_key}

    if node["type"] == "File" and ctx is not None:
        # Phase 2 step 2 (module_file_bridge): richer discovery/graph.json
        # context for a File node, joined at query time -- never persisted
        # into .devkb/ itself, the two stores stay independent per the ADR.
        discovery_graph_path = ctx.repo_root / ".onboarding" / "graph.json"
        module_key = file_to_module(discovery_graph_path, ctx.repo_root).get(node["natural_key"])
        if module_key:
            node = {**node, "properties": {**node["properties"], "discovery_module": module_key}}


    outgoing = _ranked(
        [{"verb": e["verb"], "to": _linked_summary(idx.by_uid[e["to_uid"]]), "evidence": e["properties"]}
         for e in idx.out_edges.get(node["uid"], [])
         if e["to_uid"] in idx.by_uid])
    incoming = _ranked(
        [{"verb": e["verb"], "from": _linked_summary(idx.by_uid[e["from_uid"]]), "evidence": e["properties"]}
         for e in idx.in_edges.get(node["uid"], [])
         if e["from_uid"] in idx.by_uid])
    bundle = {"found": True, "node": node,
              "outgoing": outgoing["links"], "incoming": incoming["links"]}
    omitted = {
        verb: outgoing["omitted"].get(verb, 0) + incoming["omitted"].get(verb, 0)
        for verb in set(outgoing["omitted"]) | set(incoming["omitted"])
    }
    if omitted:
        # Named `omitted_by_verb` rather than a bare count: "673 hidden" tells
        # a reader nothing, "673 SIMILAR_TO below the top 10 by weighted
        # overlap" tells them whether they care.
        bundle["omitted_by_verb"] = omitted
        bundle["ranked_by"] = "weighted_score"
    return bundle


#: ADR-SDP-DEVKB-002 §2: `Epic`/`Story` are query aliases for
#: `Ticket{ticket_type: EPIC|STORY}`; `tickets` is every Ticket. A Ticket with
#: no `ticket_type` (a graph built before BL-14) is a plain ticket, so it only
#: ever answers to `tickets`.
_TICKET_ALIASES: dict[str, str | None] = {"stories": "STORY", "epics": "EPIC", "tickets": None}
_QUESTION_RE = re.compile(r"^\s*(stories|epics|tickets)\s+implementing\s+(\S+)\s*$", re.IGNORECASE)


def _resolve_spec(idx: DevKBIndex, ref: str) -> list[dict[str, Any]]:
    """Spec nodes `ref` names: its path (natural key) first, else its `spec_id`.
    More than one means the id is ambiguous -- the build links none of them by
    it (`extractors/lifecycle.py`), and `implementing` answers the same way."""
    node = idx.node("Spec", ref)
    if node is not None:
        return [node]
    return sorted(
        (n for n in idx.by_type.get("Spec", []) if n.get("properties", {}).get("spec_id") == ref),
        key=lambda n: n["natural_key"],
    )


def implementing(idx: DevKBIndex, kind: str, ref: str) -> dict[str, Any]:
    """Tickets with an `IMPLEMENTS` edge to the spec `ref` (a SPEC id or a
    path), filtered by the Epic/Story alias. `found` is about the SPEC: a
    known spec nothing implements yet is `found: true` with no results."""
    kind = kind.lower()
    wanted = _TICKET_ALIASES[kind]
    specs = _resolve_spec(idx, ref)
    if not specs:
        return {"found": False, "question": f"{kind} implementing {ref}", "spec": ref}
    if len(specs) > 1:
        return {"found": False, "question": f"{kind} implementing {ref}", "spec": ref,
                "ambiguous": [s["natural_key"] for s in specs]}
    results: dict[str, dict[str, Any]] = {}
    for spec in specs:
        for e in idx.in_edges.get(spec["uid"], []):
            if e["verb"] != "IMPLEMENTS":
                continue
            ticket = idx.by_uid.get(e["from_uid"])
            if ticket is None or ticket["type"] != "Ticket":
                continue
            props = ticket.get("properties", {})
            # ADR-DEVKB-007: a hosted issue with sub-issues is an epic whatever its type says
            if wanted is not None and props.get("ticket_type") != wanted and not (wanted == "EPIC" and props.get("epic")):
                continue
            results[ticket["natural_key"]] = {
                **_linked_summary(ticket),
                "ticket_type": props.get("ticket_type"),
                "status": props.get("status"),
                "spec": spec["natural_key"],
                "evidence_ref": e["properties"].get("evidence_ref"),
            }
    return {
        "found": True, "question": f"{kind} implementing {ref}",
        "specs": [_linked_summary(s) for s in specs],
        "count": len(results),
        "results": [results[k] for k in sorted(results)],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Query the devkb graph for one project")
    ap.add_argument("--project", required=True, help="Project code, e.g. ODSF")
    ap.add_argument("--about", help="A ticket id, WP id, or milestone id")
    ap.add_argument(
        "question", nargs="*",
        help='a question instead of --about: "stories|epics|tickets implementing <SPEC-id|spec path>"',
    )
    args = ap.parse_args()
    question = " ".join(args.question).strip()
    if bool(args.about) == bool(question):
        ap.error("give exactly one of --about KEY or a question "
                 '("stories implementing SPEC-ODSF-003")')
    match = _QUESTION_RE.match(question) if question else None
    if question and match is None:
        ap.error(f"unrecognised question {question!r}; expected "
                 '"stories|epics|tickets implementing <SPEC-id|spec path>"')

    try:
        ctx = resolve(args.project)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not (ctx.devkb_dir / "manifest.json").exists():
        print(f"Error: {_STALE_HINT.format(code=args.project)}", file=sys.stderr)
        return 1

    idx = load(ctx.devkb_dir)
    if match is not None:
        bundle = implementing(idx, match.group(1), match.group(2))
    else:
        bundle = context_bundle(idx, args.about, ctx)
    print(json.dumps(bundle, indent=2))
    return 0 if bundle["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
