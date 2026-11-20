"""#331: the arms run the same suite; the table shows each arm's start (first-call context, tests collected) apart from totals."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")
rt = importlib.import_module("release_table")


def _checkout(tmp_path, monkeypatch, arm):
    """The arm's real checkout of this repository's HEAD, with uv, the base suite and graph builds stubbed."""
    real_run = subprocess.run

    def run(cmd, *a, **k):
        c = [str(x) for x in cmd]
        if c[0].endswith(".venv/bin/python") or c[0].endswith("/build") or c[0].endswith("devkb"):
            return subprocess.CompletedProcess(cmd, 0, "698 tests collected in 0.4s\n", "")
        return real_run(cmd, *a, **k)

    real_sh = sb.sh
    monkeypatch.setattr(pb.subprocess, "run", run)
    monkeypatch.setattr(sb, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "") if cmd[0] == "uv" else real_sh(cmd, **kw))
    monkeypatch.setattr(sb, "REPO", HERE)
    monkeypatch.setattr(sb, "CORPUS_REPOS", ())
    monkeypatch.setattr(sb, "check_graphs", lambda w: None)
    monkeypatch.setitem(pb.BASES, arm, "HEAD")
    w = tmp_path / arm
    pb.checkout(w, arm)
    return w


def _tests(w):
    return sorted(p.name for p in (w / "tests").glob("*.py"))


def test_the_none_arm_and_a_devkb_arm_have_the_same_test_files(tmp_path, monkeypatch):
    monkeypatch.delenv("POLICY_EQUAL_SUITE", raising=False)
    none, dk = _tests(_checkout(tmp_path, monkeypatch, "none")), _tests(_checkout(tmp_path, monkeypatch, "climain"))
    assert none == dk and len(none) > 50


def test_the_devkb_arm_keeps_the_guardrail_scripts_the_none_arm_loses(tmp_path, monkeypatch):
    monkeypatch.delenv("POLICY_EQUAL_SUITE", raising=False)
    assert not list((_checkout(tmp_path, monkeypatch, "none") / "scripts").glob("devkb_guardrail*.py"))
    assert (_checkout(tmp_path, monkeypatch, "climain") / "scripts" / "devkb_guardrail.py").exists()


def test_nonekeep_and_the_opt_out_keep_every_test(tmp_path, monkeypatch):
    monkeypatch.delenv("POLICY_EQUAL_SUITE", raising=False)
    keep = _tests(_checkout(tmp_path, monkeypatch, "nonekeep"))
    assert "test_devkb_guardrail.py" in keep
    monkeypatch.setenv("POLICY_EQUAL_SUITE", "0")
    assert _tests(_checkout(tmp_path, monkeypatch, "climain")) == keep


def test_trim_tests_removes_guardrail_tests_and_their_dependents_only(tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    (t / "test_a.py").write_text("import devkb_guardrail\n")
    (t / "test_b.py").write_text("from test_a import x\n")
    (t / "test_c.py").write_text("def test_c():\n    pass\n")
    pb.trim_tests(tmp_path)
    assert _tests(tmp_path) == ["test_c.py"]


def test_collected_reads_the_last_line_and_gives_none_otherwise():
    assert pb.collected("a\nb\n986 tests collected in 0.41s\n") == 986
    assert pb.collected("1 test collected in 0.1s") == 1
    assert pb.collected("error: no tests ran") is None and pb.collected("") is None


def test_a_transcript_reports_its_first_calls_context(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    ms = [{"type": "assistant", "message": {"id": f"m{i}", "usage": {"input_tokens": 10 * i, "cache_read_input_tokens": 1000 * i,
                                                                    "output_tokens": 1}, "content": []}} for i in (1, 2)]
    p = tmp_path / "s.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in ms))
    assert sb.transcript(p)["first_ctx"] == 1010


def _row(arm, tests, first):
    return {"run": f"x-{arm}-r1", "issue": "9", "arm": arm, "rep": "1", "turns": 3, "calls": {}, "ctx_tokens": 1, "cost": 1.0,
            "seconds": 60, "suite_pass": True, "devkb_nav": 0, "devkb_selftest": 0, "acceptance": {"pass": True},
            "tests_collected": tests, "first_ctx": first}


def test_the_table_warns_when_the_arms_collect_different_numbers_of_tests(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    out = rt.table([("9", [_row("none", 675, 23500), _row("main", 986, 26800)])])
    assert "| #9 | none | 23.5 | 675 |" in out and "| #9 | main | 26.8 | 986 |" in out
    assert "WARNING #9: the arms collect different numbers of tests" in out


def test_equal_counts_give_no_warning_and_missing_counts_read_unknown(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    same = rt.table([("9", [_row("none", 698, 1), _row("main", 698, 2)])])
    assert "WARNING" not in same
    old = rt.table([("9", [_row("none", None, 1), _row("main", None, 2)])])
    assert "unknown" in old and "WARNING" not in old


def test_rows_scored_before_this_change_have_no_start_figures_and_the_table_still_prints(monkeypatch):
    monkeypatch.setattr(rt, "guard_rows", lambda s: [])
    old = {k: v for k, v in _row("none", 1, 1).items() if k not in ("tests_collected", "first_ctx")}
    out = rt.table([("9", [old, {**old, "arm": "main"}])])
    assert "| #9 | none | unknown | unknown |" in out and "WARNING" not in out


def test_the_template_key_includes_the_suite_setting_so_an_old_or_other_template_is_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "TEMPLATES", tmp_path)
    monkeypatch.setattr(sb, "REPO", HERE)
    monkeypatch.setitem(pb.BASES, "climain", "HEAD")
    built = []
    monkeypatch.setattr(pb, "checkout", lambda t, arm: (built.append(Path(t).name), Path(t).mkdir(parents=True))[0])
    (tmp_path / "climain-oldtemplate-without-the-suite-in-its-name").mkdir()
    monkeypatch.delenv("POLICY_EQUAL_SUITE", raising=False)
    eq = pb.template_for("climain")
    monkeypatch.setenv("POLICY_EQUAL_SUITE", "0")
    full = pb.template_for("climain")
    assert eq != full and eq.name.endswith("-suiteeq") and full.name.endswith("-suitefull")
    assert pb.template_for("climain") == full and len(built) == 2                  # same setting: reused, not rebuilt
