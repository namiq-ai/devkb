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
    assert set(pb.ENV_REF) == {"release", "main"}
    env = {"hook": "/e/src/scripts/devkb_guardrail.py", "post": "/nonexistent/post.py", "bin": "/e/.venv/bin/devkb"}
    hooks = toolenv.hooks_settings(env)
    cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert "/e/src/scripts/devkb_guardrail.py" in cmd and "CLAUDE_PROJECT_DIR" not in cmd
    assert hooks["PreToolUse"][0]["matcher"] == "Read|Grep|Bash"
    assert pb.tool_of("main", env) == "/e/.venv/bin/devkb"


def test_runs_never_load_the_users_own_settings():
    assert pb.SOURCES == ["--setting-sources", "project,local"]
