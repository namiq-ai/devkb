"""#305: a setup error is recorded as an error and retried; a run refused for a red base is set up again next batch."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")


def _attempt(tmp_path, monkeypatch, end, exc):
    monkeypatch.setattr(pb, "B", tmp_path)
    out = tmp_path / "runs" / "p9-none-r1"
    out.mkdir(parents=True)
    if end is not None:
        (out / "end").write_text(json.dumps(end))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise exc

    monkeypatch.setattr(pb, "template_for", lambda arm, issue=None: "x")
    monkeypatch.setattr(pb, "from_template", boom)
    monkeypatch.setattr(pb, "checkout", boom)
    msg = pb._run_one("9", "none", 1)
    return msg, bool(calls), json.loads((out / "end").read_text()) if (out / "end").exists() else None


def test_a_run_refused_for_a_red_base_is_set_up_again_in_the_next_batch(tmp_path, monkeypatch):
    msg, tried, end = _attempt(tmp_path, monkeypatch, {"exit": "base-red", "seconds": 0}, RuntimeError("base is red"))
    assert tried and not msg.startswith("skip") and end["exit"] == "base-red"      # still red: recorded again


def test_a_setup_error_is_an_error_not_a_red_base(tmp_path, monkeypatch):
    msg, tried, end = _attempt(tmp_path, monkeypatch, None, OSError("uv pip install: connection reset"))
    assert tried and end["exit"] == "error" and "connection reset" in end["error"] and msg.startswith("error")


def test_a_recorded_setup_error_is_retried(tmp_path, monkeypatch):
    msg, tried, end = _attempt(tmp_path, monkeypatch, {"exit": "error", "seconds": 0}, OSError("connection reset"))
    assert tried and end["exit"] == "error"


def test_a_finished_run_is_still_skipped(tmp_path, monkeypatch):
    msg, tried, end = _attempt(tmp_path, monkeypatch, {"exit": 0, "seconds": 5}, RuntimeError("not reached"))
    assert not tried and msg.startswith("skip")
