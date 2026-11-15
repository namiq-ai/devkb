"""`pipeline detail`: per-task cells, score parts per kind and graph tools per arm, from a runs file."""
from devkb.bench.pipeline import detail_table


def _run(task, kind, arm, cost, score, turns, parts, tools=()):
    return {"task": task, "kind": kind, "arm": arm, "cost": cost, "score": score, "turns": turns,
            "parts": parts, "graph_tools": list(tools)}


def test_detail_table_cells_parts_and_tools():
    rows = [
        _run("T1", "rca", "plain", 0.10, 0.5, 10, {"callers": 0.5, "tests": 0.5}),
        _run("T1", "rca", "plain", 0.30, 1.0, 12, {"callers": 1.0, "tests": 1.0}),
        _run("T1", "rca", "lean", 0.02, 1.0, 4, {"callers": 1.0, "tests": 1.0}, ["callers", "callers", "tests_for"]),
        _run("T2", "refactor", "plain", 0.01, 1.0, 2, {"files": 1.0}),
    ]
    out = detail_table(rows)
    assert "| kind | task | plain | lean |" in out
    assert "| rca | T1 | 0.200 / 0.75 / 11 | 0.020 / 1.00 / 4 |" in out
    assert "| refactor | T2 | 0.010 / 1.00 / 2 | — |" in out
    assert "| plain | 0.75 | 0.75 | 2 |" in out
    assert "- **lean**: $0.02 in all; `callers` 2, `tests_for` 1" in out
    assert "- **plain**: $0.41 in all; none" in out


def test_a_tool_arm_that_never_called_the_graph_is_flagged():
    from devkb.bench.pipeline import tool_arms_without_tools
    rows = [{"arm": "plain", "graph_calls": 0}, {"arm": "core", "graph_calls": 0}, {"arm": "core", "graph_calls": 0},
            {"arm": "lean", "graph_calls": 0}, {"arm": "lean", "graph_calls": 3}, {"arm": "pack", "graph_calls": 0}]
    assert tool_arms_without_tools(rows) == ["core"]
