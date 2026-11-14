"""TestCase for every test function, not only those that name a ticket (ODSF-304).

`files_tests.py` creates a TestCase only where a ticket id sits near a test, so
a project whose tests never mention tickets (ODSF's own, and nearly all of
another's) had almost no TestCase nodes at all. This inventories every test
function that `devkb.test_discovery` finds and links it to its file with
DEFINED_IN (ADR-SDP-DEVKB-003).

Node identity is `path:line`, the same key `files_tests.py` uses, so a test
that is both inventoried and ticket-marked is one node carrying both sets of
properties (DevKBGraph merges props on a repeated key).
"""
from __future__ import annotations

from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext
from devkb.test_discovery import list_test_files, tests_in_file


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()
    for rel in list_test_files(ctx.repo_root, ctx.tests_dir):
        framework = "pytest" if rel.endswith(".py") else "js"
        cases = tests_in_file(ctx.repo_root, rel)
        if not cases:
            continue
        g.add_node("File", rel, source="test-inventory")
        for name, line in cases:
            key = f"{rel}:{line}"
            g.add_node(
                "TestCase", key, source="test-inventory",
                file=rel, line=line, function=name, framework=framework,
            )
            g.add_edge(
                "DEFINED_IN", "TestCase", key, "File", rel,
                source="test-inventory", confidence=1.0, evidence_ref=f"{rel}:{line}",
            )
    return g
