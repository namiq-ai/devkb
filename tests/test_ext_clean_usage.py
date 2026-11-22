"""The external benchmark's clean mode and its usage analysis (0.2.15)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    sys.path.insert(0, str(ROOT / "bench" / "policy"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "bench" / "ext" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_clean_root_names_neither_the_tool_nor_an_arm(monkeypatch, tmp_path):
    monkeypatch.delenv("EXT_CLEAN_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "u"))      # the default root is under $HOME: not this machine's
    eb = load("extbench")
    assert not [x for x in eb.LEAKS if x in str(eb.CLEAN / "w0123abcd").lower()], eb.CLEAN


def test_a_root_that_names_an_arm_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("EXT_CLEAN_ROOT", str(tmp_path / "ship-arm"))
    eb = load("extbench")
    monkeypatch.setattr(eb, "arm_env", lambda spec: ("devkb", {"bin": "/x"}))
    monkeypatch.setattr(eb, "RUNS", tmp_path / "runs")                     # not the cache: a real earlier run would be reported as a skip
    out = eb.run_one({"id": "y1"}, "devkb=abc", 1, clean=True)
    assert out.startswith("refused") and "ship" in out and not (tmp_path / "ship-arm").exists()


def _stream(path, calls):
    ev = []
    for i, (cmd, out) in enumerate(calls):
        ev.append({"message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": cmd}}]}})
        ev.append({"message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": out}]}})
    path.write_text("\n".join(json.dumps(e) for e in ev))


def test_usage_reports_first_action_answer_fix_file_and_what_followed(tmp_path):
    us = load("usage")
    run = tmp_path / "y2-devkb-r1"
    run.mkdir()
    _stream(run / "stream.jsonl", [('devkb symbol "Emitter::EmitBeginDoc" --source; grep -n tag src/emitter.cpp', "src/emitter.cpp L181-205 def EmitBeginDoc"),
                                   ("sed -n 1,20p src/emitter.cpp", "..."), ("devkb uses SetTag", "no match for SetTag")])
    r = us.analyse(run, {"src/emitter.cpp"})
    first, second = r["nav"]
    assert (first["pos"], first["sub"], first["answered"], first["fixfile"], first["also_grep_same_call"]) == (1, "symbol", True, True, True)
    assert first["next"] == "Bash:sed"
    assert (second["pos"], second["answered"], second["fixfile"]) == (3, False, False)
