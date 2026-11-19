"""#209: the benchmark counts guardrail firings, not pass-throughs. #210: an absolute Read after a relative listing of
the same folder counts as a read in it."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sys.path.insert(0, str(ROOT / "bench" / "exploration"))
sb = importlib.import_module("storybench")
lr = importlib.import_module("listing_then_read")


def test_pass_throughs_are_not_firings(tmp_path):
    log = tmp_path / "g.log"
    rows = [{"session": "s1", "action": a} for a in ["pass-through"] * 7 + ["remind"]] + [{"session": "s2", "action": "substitute"}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    fired, acts = sb.guardrail_actions("s1", log)
    assert fired == 1 and acts == {"pass-through": 7, "remind": 1}


def test_an_absolute_read_after_a_relative_listing_is_in_that_folder(tmp_path):
    s = tmp_path / "stream.jsonl"
    ev = [{"type": "system", "subtype": "init", "cwd": "/work"},
          {"message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls devkb"}}]}},
          {"message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/work/devkb/cli.py"}}]}}]
    s.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    got = list(lr.events(s))
    assert ("list", "devkb", "ls") in got and ("read", "devkb/cli.py", "Read") in got
