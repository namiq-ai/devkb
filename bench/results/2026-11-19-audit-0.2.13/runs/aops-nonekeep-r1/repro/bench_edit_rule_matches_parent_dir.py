"""Editing a test in a checkout that lives under a directory named `devkb` must not turn every later devkb query into a self-test (#258)."""
import json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import storybench as sb

tmp = Path(tempfile.mkdtemp())
s = tmp / "stream.jsonl"
ev = [
    {"type": "system", "subtype": "init", "session_id": "s"},
    # the agent edits only a test, by the absolute path Claude Code requires, in a checkout under .../devkb/bench/policy/work/
    {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "id": "t1", "name": "Edit",
        "input": {"file_path": "/home/u/devkb/bench/policy/work/p1-main-r1/tests/test_x.py"}}]}},
    {"type": "assistant", "message": {"id": "m2", "content": [{"type": "tool_use", "id": "t2", "name": "Bash",
        "input": {"command": "devkb symbol parse_args"}}]}},
    {"type": "result", "usage": {}, "total_cost_usd": 0},
]
s.write_text("".join(json.dumps(e) + "\n" for e in ev))
r = sb.transcript(s)
print(f"devkb_nav={r['devkb_nav']} devkb_selftest={r['devkb_selftest']}")
print("expected: the query is navigation (nav=1, selftest=0): no devkb code was edited; actual: counted as a self-test because "
      "the path contains a `devkb/` directory")
sys.exit(1 if r["devkb_selftest"] else 0)
