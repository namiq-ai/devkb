"""#380: `policybench score` goes on past a run with an unknown cost. #379: each run has its own MCP config, written atomically; a run that died of a setup
error before the model is not scored and is run again."""
import importlib
import json
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
pb = importlib.import_module("policybench")


def _row(run, cost):
    return {"run": run, "issue": "9", "arm": "none", "acceptance": {"pass": True}, "suite_pass": True, "cost": cost, "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": []}


def test_score_prints_cost_unknown_and_goes_on(monkeypatch, tmp_path, capsys):
    runs = tmp_path / "runs"
    for name in ("p9-none-r1", "p9-none-r2", "p9-none-r3"):
        (runs / name).mkdir(parents=True)
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "score_run", lambda issue, out: _row(out.name, None if out.name.endswith("r2") else 0.25))
    pb.score(["9"])
    out = capsys.readouterr().out
    assert "p9-none-r1 pass suite $0.25" in out and "p9-none-r2 pass suite cost ?" in out and "p9-none-r3 pass suite $0.25" in out, out


def test_a_run_that_died_of_a_setup_error_is_not_scored_and_not_finished(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pb, "B", tmp_path)
    d = tmp_path / "runs" / "p9-none-r1"
    d.mkdir(parents=True)
    (d / "stream.jsonl").write_text("")
    (d / "stderr.log").write_text("Error: Invalid MCP configuration:\nMCP config is not a valid JSON\n")
    (d / "end").write_text(json.dumps({"exit": 1}))
    assert "Invalid MCP configuration" in pb.setup_error(d)
    assert not pb.finished("9", "none", 1), "it is set up again, not skipped by --resume"
    monkeypatch.setattr(pb, "score_run", lambda issue, out: (_ for _ in ()).throw(AssertionError("scored a setup error")))
    pb.score(["9"])
    assert "SETUP ERROR (not scored; run again)" in capsys.readouterr().out


def test_a_run_with_a_stream_or_without_an_error_line_is_not_a_setup_error(tmp_path):
    d = tmp_path / "p9-none-r1"
    d.mkdir()
    (d / "stderr.log").write_text("Error: something\n")
    (d / "stream.jsonl").write_text('{"type": "system"}\n')
    assert pb.setup_error(d) is None                     # it reached the model
    (d / "stream.jsonl").write_text("")
    (d / "stderr.log").write_text("warning: slow\n")
    assert pb.setup_error(d) is None                     # no error line named


def test_the_empty_mcp_config_is_never_read_half_written(tmp_path):
    """The write the run does (a temporary file, then os.replace) against a reader looping on the same path."""
    import os
    path = tmp_path / "no-mcp.json"
    stop, bad = threading.Event(), []

    def writer():
        i = 0
        while not stop.is_set():
            tmp = tmp_path / f".t{i % 4}.tmp"
            tmp.write_text(json.dumps({"mcpServers": {}}))
            os.replace(tmp, path)
            i += 1
    path.write_text(json.dumps({"mcpServers": {}}))
    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(3000):
            try:
                json.loads(path.read_text())
            except ValueError as e:
                bad.append(e)
    finally:
        stop.set()
        t.join()
    assert not bad, bad[:2]


def test_run_one_gives_each_run_its_own_config():
    src = (HERE / "bench" / "policy" / "policybench.py").read_text()
    assert 'mcp = str(B / "no-mcp.json")' not in src and 'mcp = str(out / "no-mcp.json")' in src
