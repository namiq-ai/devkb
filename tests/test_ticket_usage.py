"""bench/audit/ticket_usage.py: the intervals and what is counted inside them."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "audit"))
import ticket_usage as tu  # noqa: E402


def test_intervals_pair_starts_with_ends_and_leave_an_open_one_running():
    marks = [{"t": "2026-11-22T10:00:00", "event": "start", "ticket": "1"}, {"t": "2026-11-22T11:00:00", "event": "end", "ticket": "1"},
             {"t": "2026-11-22T11:00:01", "event": "start", "ticket": "2"}, {"t": "2026-11-22T09:00:00", "event": "end", "ticket": "9"}]
    iv = tu.intervals(marks)
    assert iv[0] == ("1", "2026-11-22T10:00:00", "2026-11-22T11:00:00") and iv[1][0] == "2" and len(iv) == 2, "an end with no start is ignored"


def test_telemetry_and_guard_decisions_count_only_inside_the_interval(tmp_path):
    import datetime as dt
    ts = lambda s: dt.datetime.fromisoformat(s).timestamp()
    tel = tmp_path / "t.jsonl"
    tel.write_text("\n".join(json.dumps({"t": ts(s), "tool": k, "ms": 1, "bytes": 1, "ok": True}) for s, k in
                             [("2026-11-22T10:30:00", "pack"), ("2026-11-22T10:40:00", "symbol"), ("2026-11-22T12:00:00", "pack")]))
    g = tmp_path / "g.log"
    g.write_text("\n".join(json.dumps(r) for r in [
        {"t": "2026-11-22T10:31:00", "session": "abc1", "action": "alongside"}, {"t": "2026-11-22T10:32:00", "session": "abc1", "action": "pass-through", "reason": "stale-graph"},
        {"t": "2026-11-22T10:33:00", "session": "zzz", "action": "alongside"}, {"t": "2026-11-22T10:34:00", "session": "abc1", "action": "remind"},
        {"t": "2026-11-22T13:00:00", "session": "abc1", "action": "alongside"}]))
    u = tu.usage("2026-11-22T10:00:00", "2026-11-22T11:00:00", "abc", guard=g, telemetry=tel)
    assert u["queries"] == 2 and u["by_tool"] == {"pack": 1, "symbol": 1}
    assert (u["decisions"], u["answered"], u["stale"]) == (2, 1, 1), "another session, a reminder and a later decision do not count"
