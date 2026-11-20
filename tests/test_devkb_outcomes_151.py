"""#151 + #149: every call records its outcome; `devkb stats` and `devkb guardrail-stats` count them."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_devkb_graph_misses_133 import PRE, ROOT, run  # noqa: E402
from test_devkb_graph_misses_133 import repo  # noqa: E402,F401  (fixture)


def lines(repo):
    f = repo / ".devkb" / "process-api-telemetry.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def test_every_call_records_its_outcome(repo, monkeypatch):
    monkeypatch.delenv("DEVKB_TELEMETRY", raising=False)
    sys.path.insert(0, str(ROOT))
    from devkb.packs import Packer, logged_pack
    from devkb.process_api import ProcessAPI
    api = ProcessAPI(str(repo), telemetry_source="cli")
    p = Packer(api)
    n0 = len(lines(repo))
    api.call("symbol", query="pkg/alpha.py::extract")
    api.call("symbol", query="zz_nothing_here")
    logged_pack(p, "change", "extract")
    logged_pack(p, "change", "lone_method")
    logged_pack(p, "change", "phantom_name")
    logged_pack(p, "change", "run")
    api.call("symbol", query="x", bogus=1)                   # bad arguments
    rows = lines(repo)[n0:]
    got = [(x["tool"], x["outcome"]) for x in rows if x["tool"] != "uses"]
    assert got == [("symbol", "complete"), ("symbol", "no-match"), ("pack", "complete"), ("pack", "incomplete"),
                   ("pack", "fallback-text"), ("pack", "ambiguous"), ("symbol", "refused")]
    assert rows[0]["resolved"].endswith("alpha.py::extract")
    inc = next(x for x in rows if x.get("outcome") == "incomplete")
    assert "Incomplete" in inc["detail"] and len(inc["detail"]) <= 200
    assert next(x for x in rows if x["tool"] == "pack" and x["outcome"] == "complete")["resolved"].endswith("::extract")

    e = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    out = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "stats", "--project", str(repo)], cwd=repo, env=e,
                         capture_output=True, text=True, timeout=60).stdout
    assert "pack" in out and "fallback-text" in out and "total:" in out


def test_guardrail_logs_one_line_per_action_and_stats_counts_them(repo, tmp_path):
    def go(pattern, n, cmd=None):
        ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": "g1", "tool_use_id": f"g{n}",
              "tool_input": {"command": cmd or f"grep -rn '{pattern}' ."}}
        run(PRE, tmp_path, ev)

    go("extract", 1)                                                   # substitute
    go("extract", 2)                                                   # the identical search again: repeat
    go("extract", 3, cmd="grep -n '^def ' pkg/alpha.py && echo done")    # a file's definitions: its outline, alongside
    go("lone_method", 4)                                               # incomplete: pass-through
    f = tmp_path / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    assert [r["action"] for r in rows if r.get("action") != "remind"] == ["substitute", "repeat", "alongside", "pass-through"]
    rows = [r for r in rows if r.get("action") != "remind"]
    r = rows[0]
    assert r["names"] == ["extract"] and r["verdicts"] == ["complete"] and r["chars"] > 0
    assert r["session"] == "g1" and r["repo"] == str(repo) and r["tool"] == "Bash"
    assert [r["verdicts"] for r in rows if r.get("action") == "pass-through"] == [["incomplete"]]
    e = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore", HOME=str(tmp_path))
    out = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "guardrail-stats"], cwd=repo, env=e,
                         capture_output=True, text=True, timeout=60).stdout
    assert "substitute 1, read-answer 0, alongside 1, span-hint 0, teach 0, remind 1, pass-through 1, repeat 1" in out  # every action (#214)
    assert "incomplete 1" in out and "session g1" in out and "intent by action:" in out
