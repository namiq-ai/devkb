"""A Zephyr benchmark agent is held inside its own run (#451). That the sandbox holds on a host is `zbench.py isolation`; these pin what is asked of it."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "zephyr"))
import isolation  # noqa: E402
import zbench  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the harness and its sandbox are for Linux hosts")


def test_the_agent_gets_none_of_the_launching_sessions_variables_and_its_own_folders(tmp_path):
    env = {"PATH": "/usr/bin", "CLAUDECODE": "1", "CLAUDE_EFFORT": "max", "CLAUDE_CODE_SESSION_ID": "x", "TMPDIR": "/shared",
           "CLAUDE_CONFIG_DIR": "/cfg", "CLAUDE_CODE_OAUTH_TOKEN": "t"}
    out = isolation.agent_env(env, tmp_path)
    assert {k for k in out if k.startswith("CLAUDE")} == {"CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_TMPDIR"}
    assert out["PATH"] == "/usr/bin"
    for k in ("TMPDIR", "CLAUDE_CODE_TMPDIR", "XDG_CACHE_HOME"):
        assert Path(out[k]).is_relative_to(tmp_path), k
    assert env["TMPDIR"] == "/shared"                       # the caller's environment is left as it was


def test_two_runs_never_share_a_scratch_folder(tmp_path):
    a = isolation.scratch(tmp_path / "none" / "z1-none-r0")
    assert a == isolation.scratch(tmp_path / "none" / "z1-none-r0")
    assert a != isolation.scratch(tmp_path / "other" / "z1-none-r0")       # same tag in another batch folder
    assert a != isolation.scratch(tmp_path / "none" / "z1-none-r1")


def test_the_settings_fail_closed_and_open_only_the_scratch_folder(tmp_path):
    s = isolation.settings(tmp_path / "box", [tmp_path / "git"], [tmp_path / "hidden"])
    box = s["sandbox"]
    assert box["enabled"] and box["failIfUnavailable"] and box["allowUnsandboxedCommands"] is False
    assert "excludedCommands" not in box                    # each entry would run outside the sandbox
    assert box["filesystem"]["allowWrite"] == [str(tmp_path / "box")]
    assert str(tmp_path / "git") in box["filesystem"]["denyWrite"]
    # local sockets are not filtered by the sandbox here, so the folders that hold them are hidden
    assert box["network"]["allowAllUnixSockets"] is True
    assert {"/run", "/tmp", str(tmp_path / "hidden")} <= set(box["filesystem"]["denyRead"])
    assert s["permissions"]["blockWritesOutsideWorkingDirectories"] is True


def test_every_agent_run_is_started_sandboxed_with_its_own_temp_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ZBENCH_SCRATCH", str(tmp_path / "scratch"))
    monkeypatch.setenv("CLAUDE_EFFORT", "max")
    monkeypatch.setattr(zbench, "RUN", tmp_path / "run")
    monkeypatch.setattr(zbench, "env_for", lambda arm, w, run_dir: dict(__import__("os").environ))
    seen = {}

    def fake(cmd, cwd=None, env=None, **kw):
        seen.update(cmd=cmd, env=env, tmp_existed=Path(env["TMPDIR"]).is_dir())
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(zbench.subprocess, "run", fake)
    run_dir = tmp_path / "out" / "z1-none-r0"
    run_dir.mkdir(parents=True)
    zbench.run_agent(tmp_path / "w", "none", "p", run_dir)
    asked = json.loads(seen["cmd"][seen["cmd"].index("--settings") + 1])
    denied = asked["sandbox"]["filesystem"]["denyWrite"]
    assert asked["sandbox"]["failIfUnavailable"] is True
    for p in (zbench.ZSRC / ".git", zbench.RUN / "hidden", zbench.RUN / "tasks", zbench.OUT):
        assert str(p) in denied, p
    assert seen["tmp_existed"] and "CLAUDE_EFFORT" not in seen["env"]
    assert not isolation.scratch(run_dir).exists()          # removed after the run
