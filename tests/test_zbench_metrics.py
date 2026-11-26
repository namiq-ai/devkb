"""bench/zephyr/metrics.py reads a `claude -p` stream-json file into one flat record (#447)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "zephyr"))
import metrics  # noqa: E402


def ev(t, **kw):
    return json.dumps({"type": t, **kw})


def stream(tmp_path, events):
    p = tmp_path / "stream.jsonl"
    p.write_text("\n".join(events) + "\n")
    return p


def assistant(mid, *blocks, out=5):
    return ev("assistant", message={"id": mid, "content": list(blocks), "usage": {"input_tokens": 2, "output_tokens": out,
                                                                                 "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100}})


def use(tid, name, **inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def result_of(tid, text, error=False):
    return ev("user", message={"content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]})


def test_shell_kinds():
    assert metrics.shell_kind("cd x && grep -rn foo .") == "grep"
    assert metrics.shell_kind("devkb symbol foo --project .") == "devkb"
    assert metrics.shell_kind("/a/b/codebase-memory-mcp cli search_graph") == "cbm_cli"
    assert metrics.shell_kind("ninja -C build") == "build_test"
    assert metrics.shell_kind("sed -n 1,20p a.c") == "readcmd"
    assert metrics.shell_kind("echo hi") == "other"


def test_totals_come_from_the_result_event_not_the_per_message_placeholders(tmp_path):
    s = stream(tmp_path, [
        ev("system", subtype="init", tools=["Bash", "Read", "mcp__devkb__symbol"]),
        assistant("m1", use("t1", "Grep", pattern="x"), out=1),
        result_of("t1", "a.c:3:x"),
        ev("result", subtype="success", num_turns=2, total_cost_usd=0.5, duration_ms=1000,
           usage={"input_tokens": 4, "output_tokens": 900, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 200}, modelUsage={"claude-x": {}}),
    ])
    m = metrics.parse(s)
    assert m["tokens"]["output_tokens"] == 900 and m["tokens_by_message"]["output_tokens"] == 1
    assert m["cost_usd"] == 0.5 and m["model"] == "claude-x" and m["graph_tools_listed"] == 1
    assert m["calls_by_kind"] == {"Grep": 1}


def test_a_message_split_into_blocks_counts_as_one_turn(tmp_path):
    s = stream(tmp_path, [assistant("m1", use("t1", "Read", file_path="a.c")), assistant("m1", use("t2", "Read", file_path="b.c")),
                          result_of("t1", "x"), result_of("t2", "y")])
    assert metrics.parse(s)["turns"] == 1


def test_graph_call_outcomes_and_follow_up(tmp_path):
    s = stream(tmp_path, [
        assistant("m1", use("g1", "mcp__devkb__symbol", sym="f")), result_of("g1", "tcp.c:10 def f ... Coverage: Incomplete."),
        assistant("m2", use("s1", "Grep", pattern="f")), result_of("s1", "tcp.c:10:f"),
        assistant("m3", use("g2", "Bash", command="devkb uses g --project .")), result_of("g2", "No matches"),
        assistant("m4", use("g3", "mcp__codebase-memory-mcp__search_graph", q="h")), result_of("g3", "boom", error=True),
        assistant("m5", use("e1", "Edit", file_path="/w/tcp.c")),
    ])
    m = metrics.parse(s)
    assert [g["outcome"] for g in m["graph"]] == ["partial", "empty", "error"]
    assert m["graph"][0]["search_followed"] and m["graph"][0]["used"]
    assert m["first_graph_turn"] == 1 and m["navigation_before_first_graph"] == 0
    assert m["graph_outcomes"] == {"partial": 1, "empty": 1, "error": 1}


def test_a_run_without_a_graph_tool_has_no_first_graph_turn(tmp_path):
    s = stream(tmp_path, [assistant("m1", use("t1", "Bash", command="grep -rn x .")), result_of("t1", "a:1:x")])
    m = metrics.parse(s)
    assert m["graph_calls"] == 0 and m["first_graph_turn"] is None and m["calls_by_kind"] == {"grep": 1}
