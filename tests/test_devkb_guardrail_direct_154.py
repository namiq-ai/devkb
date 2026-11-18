"""#154: a search for a name is a direct-use question; the guardrail asks `pack refactor`, not `pack change`."""
from __future__ import annotations

import json

from test_devkb_graph_misses_133 import PRE, ROOT, repo, run  # noqa: F401  (repo is a fixture)


def test_guardrail_substitutes_the_direct_caller_pack(repo, tmp_path):
    import sys
    sys.path.insert(0, str(ROOT))
    from devkb import misses
    direct = misses.run_query(repo, "refactor", "extract")
    assert direct and direct[0] == "complete"
    ev = {"tool_name": "Grep", "cwd": str(repo), "session_id": "s154", "tool_use_id": "t154",
          "tool_input": {"pattern": "extract", "path": str(repo), "output_mode": "content"}}
    out = json.loads(run(PRE, tmp_path, ev))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "changing the signature of" in out["permissionDecisionReason"]   # the refactor pack's header


def test_run_query_asks_the_kind_it_is_given(repo):
    import sys
    sys.path.insert(0, str(ROOT))
    from devkb import misses
    assert "changing the signature of" in misses.run_query(repo, "refactor", "extract")[2]
    assert "changing the signature of" not in misses.run_query(repo, "change", "extract")[2]
