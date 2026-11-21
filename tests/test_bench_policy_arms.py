"""#221, #223, #225: benchmark arms start green, never see the hidden checks, and use the devkb they claim."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")
toolenv = importlib.import_module("toolenv")


def test_a_test_that_imports_a_removed_one_is_removed_too(tmp_path):
    (tmp_path / "test_kept.py").write_text("def test_x():\n    pass\n")
    (tmp_path / "test_uses_gone.py").write_text("from test_gone import helper\n")
    (tmp_path / "test_uses_uses.py").write_text("import test_uses_gone\n")
    pb.remove_dependents(tmp_path)
    assert sorted(p.name for p in tmp_path.glob("*.py")) == ["test_kept.py"]


def test_the_hidden_checks_are_never_in_a_checkout():
    assert "bench/policy/accept" in pb.HIDDEN


def test_tri_mode_arms_take_devkb_from_a_tool_environment():
    assert set(pb.ENV_REF) == {"release", "main", "noteach", "outline", "hookmain", "teachall",   # #218 arms; #375's pair
                               "userpolicy", "short", "inject", "userinit",                  # #366
                               "rmain", "router"}                                           # the workflow router pair
    assert pb.ARM_ENV["noteach"]["DEVKB_GUARDRAIL_TEACH"] == "0" and pb.ARM_ENV["outline"]["DEVKB_GUARDRAIL_OUTLINE"] == "1"
    assert "DEVKB_GUARDRAIL_TEACH" not in pb.ARM_ENV["main"]          # main is the hook as shipped: D1 on (#267)
    env = {"hook": "/e/src/scripts/devkb_guardrail.py", "post": "/nonexistent/post.py", "bin": "/e/.venv/bin/devkb"}
    hooks = toolenv.hooks_settings(env)
    cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert "/e/src/scripts/devkb_guardrail.py" in cmd and "CLAUDE_PROJECT_DIR" not in cmd
    assert hooks["PreToolUse"][0]["matcher"] == "Read|Grep|Bash"
    assert pb.tool_of("main", env) == "/e/.venv/bin/devkb"
    assert "UserPromptSubmit" not in hooks, "the router hook is the router arm's alone"
    routed = toolenv.hooks_settings(env, router=True)
    assert routed["UserPromptSubmit"][0]["hooks"][0]["command"].startswith('"/e/.venv/bin/devkb" hook prompt')
    assert routed["PreToolUse"] == hooks["PreToolUse"], "rmain and router differ in the prompt hook only"


def test_runs_never_load_the_users_own_settings():
    assert pb.SOURCES == ["--setting-sources", "project,local"]


def test_a_copied_template_points_its_paths_at_the_copy(tmp_path):
    t = tmp_path / "templates" / "main-x"
    (t / ".venv" / "bin").mkdir(parents=True)
    site = t / ".venv" / "lib" / "python3.11" / "site-packages"
    site.mkdir(parents=True)
    (t / ".venv" / "bin" / "pytest").write_text(f"#!{t}/.venv/bin/python\n")
    (site / "__editable___devkb_finder.py").write_text(f"MAPPING = {{'devkb': '{t}/devkb'}}\n")
    (t / ".devkb").mkdir()
    (t / ".devkb" / "symbols-manifest.json").write_text(f'{{"root": "{t}"}}')
    (t / ".bench-ready").write_text("x")
    import os
    os.utime(t / ".devkb" / "symbols-manifest.json", (1_000_000, 1_000_000))
    w = tmp_path / "work" / "p1-main-r1"
    pb.from_template(t, w)
    assert str(t) not in (w / ".venv" / "bin" / "pytest").read_text() and str(w) in (w / ".venv" / "bin" / "pytest").read_text()
    assert str(w) in (w / ".venv" / "lib" / "python3.11" / "site-packages" / "__editable___devkb_finder.py").read_text()
    assert (w / ".devkb" / "symbols-manifest.json").stat().st_mtime == 1_000_000    # freshness checks compare mtimes
    assert not (w / ".bench-ready").exists() and (t / ".bench-ready").exists()


def test_score_reuses_a_saved_row_only_while_its_hidden_check_is_unchanged(tmp_path, monkeypatch):
    import hashlib, json
    monkeypatch.setattr(pb, "B", tmp_path)
    (tmp_path / "accept").mkdir()
    (tmp_path / "accept" / "9.py").write_text("print('{}')\n")
    sha = hashlib.sha256((tmp_path / "accept" / "9.py").read_bytes()).hexdigest()
    out = tmp_path / "runs" / "p9-main-r1"
    out.mkdir(parents=True)
    (out / "end").write_text('{"exit": 0, "seconds": 1}')
    row = {"run": out.name, "issue": "9", "arm": "main", "acceptance": {"pass": True}, "suite_pass": True, "cost": 0.1,
           "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": [], "accept_sha256": sha}
    (out / "score.json").write_text(json.dumps(row))
    called = []
    monkeypatch.setattr(pb, "score_run", lambda issue, o: called.append(o) or dict(row, accept_sha256="new"))
    pb.score(["9"])
    assert called == []                                          # same check: the saved row
    (tmp_path / "accept" / "9.py").write_text("print('{\"pass\": false}')\n")
    pb.score(["9"])
    assert called == [out]                                       # the check changed: scored again


def test_a_template_is_built_once_by_two_processes_at_the_same_time(tmp_path):
    import subprocess, sys, textwrap
    code = textwrap.dedent(f"""
        import sys, time, os
        sys.path.insert(0, {str(Path(pb.__file__).parent)!r})
        import toolenv
        from pathlib import Path
        t = Path({str(tmp_path)!r}) / "t"
        with toolenv.held(Path({str(tmp_path)!r}) / ".t.lock"):
            if not (t / "ready").exists():
                t.mkdir(exist_ok=True)
                (Path({str(tmp_path)!r}) / f"built-{{os.getpid()}}").write_text("")
                time.sleep(1.5)
                (t / "ready").write_text("")
    """)
    ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(2)]
    assert [p.wait() for p in ps] == [0, 0]
    assert len(list(tmp_path.glob("built-*"))) == 1


def test_an_error_in_a_run_is_recorded_and_never_stops_the_batch(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "_run_one", lambda *a: (_ for _ in ()).throw(RuntimeError("gh: HTTP 502")))
    assert pb.run_one("9", "main", 1).startswith("error p9-main-r1")
    end = json.loads((tmp_path / "runs" / "p9-main-r1" / "end").read_text())
    assert end["exit"] == "error" and "502" in end["error"]


def test_the_hook_pair_takes_its_hooks_from_fixed_commits_and_its_checkout_from_the_batch(monkeypatch):
    """#375: hookmain and teachall run on the same checkout (the ticket's base, POLICY_MAIN) with two hook versions."""
    monkeypatch.setenv("POLICY_HOOK_MAIN", "f39cb29")
    monkeypatch.setenv("POLICY_TEACHALL", "dace8e9")
    monkeypatch.setenv("POLICY_MAIN", "4155904")
    assert pb.ENV_REF["hookmain"]() == "f39cb29" and pb.ENV_REF["teachall"]() == "dace8e9"
    assert pb.BASES["hookmain"] == pb.BASES["teachall"] == "origin/main"   # pinned to POLICY_MAIN when a batch starts
    assert pb.ARM_ENV["hookmain"] == {"DEVKB_GUARDRAIL_KEEP": "1"}
    assert pb.ARM_ENV["teachall"] == {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_TEACH_ALL": "1"}


def test_a_teachall_batch_without_its_hook_commit_stops_before_any_run(monkeypatch):
    import pytest
    monkeypatch.delenv("POLICY_TEACHALL", raising=False)
    with pytest.raises(SystemExit, match="POLICY_TEACHALL"):
        pb.check_arms(["hookmain", "teachall"])
    pb.check_arms(["hookmain", "main"])                  # no teachall: nothing to check
    monkeypatch.setenv("POLICY_TEACHALL", "dace8e9")
    pb.check_arms(["hookmain", "teachall"])
