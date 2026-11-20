"""#302: the edit rule reads the path inside the checkout; a quoted fixture path is the same fixture path."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
sb = importlib.import_module("storybench")
rt = importlib.import_module("release_table")


def _msg(i, tools):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": {"output_tokens": 1},
                                             "content": [{"type": "tool_use", "id": f"t{i}{k}", "name": n, "input": inp}
                                                         for k, (n, inp) in enumerate(tools)]}}


def _lines(cwd):
    return [{"type": "system", "subtype": "init", "session_id": "s", "cwd": cwd},
            _msg(1, [("Edit", {"file_path": f"{cwd}/docs/notes.md"})]),
            _msg(2, [("Bash", {"command": ".venv/bin/devkb outline devkb/x.py"})])]


def test_a_checkout_under_a_folder_named_devkb_is_not_an_edit_of_devkb_code(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    cwd = "/home/u/devkb/bench/work/run-1"
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in _lines(cwd)))
    t = sb.transcript(p)
    assert (t["devkb_nav"], t["devkb_selftest"]) == (1, 0)


def test_the_rule_reads_the_path_inside_the_checkout():
    root = "/home/u/devkb/work/r"
    assert sb.edits_devkb_code(root + "/devkb/cli.py", root)
    assert sb.edits_devkb_code(root + "/scripts/x.py", root)
    assert sb.edits_devkb_code("devkb/cli.py", root)
    assert not sb.edits_devkb_code(root + "/docs/devkb/notes.md", root)
    assert not sb.edits_devkb_code("/home/u/devkb/other/devkb/x.py", root)      # outside the checkout
    assert sb.edits_devkb_code("/w/devkb/x.py")                                   # no root known: as before


def test_the_release_table_uses_the_same_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "B", tmp_path)
    (tmp_path / "runs" / "r").mkdir(parents=True)
    (tmp_path / "runs" / "r" / "stream.jsonl").write_text("".join(json.dumps(x) + "\n" for x in _lines("/home/u/devkb/w")))
    assert rt.counts("r")[:2] == (1, 0)


def test_a_quoted_fixture_project_is_a_self_test_like_an_unquoted_one():
    for q in ("/tmp/fx", '"/tmp/fx"', "'/tmp/fx'"):
        assert sb.devkb_commands(f"devkb symbol foo --project {q}") == (0, 1), q
        assert sb.devkb_commands(f"devkb uses foo --project={q}") == (0, 1), q
    assert sb.devkb_commands('devkb symbol foo --project "."') == (1, 0)


def test_303_a_cut_off_runs_unknown_cost_is_left_out_of_the_mean_not_counted_as_zero():
    base = {k: 0 for k in ("turns", "grep", "nav", "own", "sub", "ctx", "out", "wall", "answers", "answer_chars")}
    rows = [{**base, "ok": True, "suite": True, "cost": 2.0}, {**base, "ok": False, "suite": False, "cost": None, "cut_off": True}]
    m = rt.summary(rows)
    assert m["cost"] == 2.0 and m["cost_lo"] == 2.0 and m["cut_off"] == 1 and m["n"] == 2
