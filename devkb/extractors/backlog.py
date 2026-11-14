"""Work package + milestone extractor (devkb Phase 1).

Ports pms-backend/pmsapp/routers/pms.py's _parse_workpackages/_parse_milestones/
_milestone_members/wp-map.json reverse-lookup logic rather than rewriting it --
that parsing is already correct and exercised daily by the live PMS board. The
port's job is only to persist it as PART_OF/BELONGS_TO edges instead of
re-deriving it on every /workpackages or /milestones request.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

_WP_ROW_RE = re.compile(
    r"\|\s*([A-Z]-\d{2,3}[a-z]?)\s*\|\s*([^|]+?)\s*\|\s*(P[012])\s*\|\s*([A-Z_]+)\s*\|"
    r"\s*([SMXL]+)\s*\|\s*([A-Z+]+)\s*\|\s*(\d+)\s*\|"
)
_MILESTONE_ROW_RE = re.compile(
    r"^\|\s*(M\d+)\s*—\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$"
)
_WP_ID_TOKEN_RE = re.compile(r"\b([A-Z]-\d{2,3}[a-z]?)\b")
_WP_ID_RANGE_RE = re.compile(r"[A-Z]-\d{2,3}[a-z]?\s*\.\.+\s*[A-Z]-\d{2,3}[a-z]?")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _parse_workpackages(text: str) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        m = _WP_ROW_RE.match(line)
        if not m:
            continue
        wp_id, title, priority, status, effort, owner, sprint = m.groups()
        by_id[wp_id] = {
            "id": wp_id, "stream": wp_id[0], "title": title.strip(),
            "priority": priority.strip(), "status": status.strip(),
            "effort": effort.strip(), "owner": owner.strip(), "sprint": sprint.strip(),
        }
    return list(by_id.values())


def _parse_milestones(text: str) -> list[dict[str, Any]]:
    in_section = False
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("## MILESTONE SUMMARY"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        m = _MILESTONE_ROW_RE.match(line)
        if m:
            mid, title, exit_condition, owner, sprint = m.groups()
            results.append({
                "id": mid, "title": title.strip(), "exit_condition": exit_condition.strip(),
                "owner": owner.strip(), "sprint": sprint.strip(),
            })
    return results


def _milestone_members(milestones: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in milestones:
        exit_cond = _WP_ID_RANGE_RE.sub(" ", m.get("exit_condition", ""))
        out[m["id"]] = set(_WP_ID_TOKEN_RE.findall(exit_cond))
    return out


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()
    if not ctx.board_file.exists():
        return g
    text = ctx.board_file.read_text()
    board_evidence = str(ctx.board_file.relative_to(ctx.repo_root))

    wps = _parse_workpackages(text)
    milestones = _parse_milestones(text)
    wp_map = _read_json(ctx.wp_map_file, {})
    members = _milestone_members(milestones)

    for m in milestones:
        g.add_node("Milestone", m["id"], source="backlog", title=m["title"],
                    exit_condition=m["exit_condition"], owner=m["owner"], sprint=m["sprint"])

    for wp in wps:
        g.add_node("WorkPackage", wp["id"], source="backlog", title=wp["title"],
                    stream=wp["stream"], priority=wp["priority"], status=wp["status"],
                    effort=wp["effort"], owner=wp["owner"], sprint=wp["sprint"])

        ticket = wp_map.get(f"wp:{wp['id']}")
        if ticket:
            g.add_edge("PART_OF", "Ticket", ticket, "WorkPackage", wp["id"],
                        source="wp-map", confidence=1.0,
                        evidence_ref=str(ctx.wp_map_file.relative_to(ctx.repo_root)))

    for milestone_id, wp_ids in members.items():
        for wp_id in wp_ids:
            g.add_edge("BELONGS_TO", "WorkPackage", wp_id, "Milestone", milestone_id,
                        source="board-milestone-summary", confidence=1.0, evidence_ref=board_evidence)

    return g
