"""`devkb hook pre-edit`: the file's pack, given at the first edit, never blocking."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkb import hook  # noqa: E402

PACK = "# Graph pack: before editing `app.py`\n\n## Functions other files call (1 of 1)\n- `run` — 1 file(s)\n\n## Coverage\n**Complete.**"


def _project(tmp_path: Path, graph: bool = True) -> Path:
    (tmp_path / "app.py").write_text("def run():\n    return 1\n")
    if graph:
        (tmp_path / ".devkb").mkdir()
        (tmp_path / ".devkb" / "nodes.jsonl").write_text("")
    return tmp_path


def _fake_pack(monkeypatch, text=PACK, code=0):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, code, text, "")
    monkeypatch.setattr(hook.subprocess, "run", run)
    return calls


def _event(project: Path, tool="Edit", path="app.py", session="s1"):
    return {"tool_name": tool, "tool_input": {"file_path": str(project / path)}, "session_id": session, "cwd": str(project)}


def test_an_edit_gets_the_pack_as_context_and_is_not_blocked(tmp_path, monkeypatch):
    calls = _fake_pack(monkeypatch)
    out = hook.pre_edit(_event(_project(tmp_path)))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and "permissionDecision" not in spec
    assert "`app.py`" in spec["additionalContext"] and "**Complete.**" in spec["additionalContext"]
    assert calls[0][-4:] == ["--project", str(tmp_path), "file", "app.py"]


def test_a_file_is_given_once_per_session_but_again_in_another(tmp_path, monkeypatch):
    _fake_pack(monkeypatch)
    p = _project(tmp_path)
    assert hook.pre_edit(_event(p)) is not None
    assert hook.pre_edit(_event(p)) is None
    assert hook.pre_edit(_event(p, session="s2")) is not None


def test_nothing_to_say_is_silence(tmp_path, monkeypatch):
    _fake_pack(monkeypatch)
    p = _project(tmp_path)
    assert hook.pre_edit(_event(p, tool="Read")) is None, "only edits"
    assert hook.pre_edit(_event(p, path="new.py")) is None, "a new file has no callers"
    assert hook.pre_edit({"tool_name": "Edit", "tool_input": {"file_path": "/etc/hosts"}, "cwd": str(p)}) is None, "outside the project"
    bare = tmp_path / "bare"
    bare.mkdir()
    assert hook.pre_edit(_event(_project(bare, graph=False))) is None, "no graph yet"
    _fake_pack(monkeypatch, text="The graph has no code for `app.py`")
    assert hook.pre_edit(_event(p, session="s9")) is None
    _fake_pack(monkeypatch, code=1)
    assert hook.pre_edit(_event(p, session="s10")) is None


def test_a_long_pack_is_cut_and_main_never_raises(tmp_path, monkeypatch, capsys):
    _fake_pack(monkeypatch, text="x\n" * 9000)
    out = hook.pre_edit(_event(_project(tmp_path)))
    assert len(out["hookSpecificOutput"]["additionalContext"]) < hook.LIMIT + 400 and "(cut;" in out["hookSpecificOutput"]["additionalContext"]
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "not json"})())
    assert hook.main(["pre-edit"]) == 0


def _bash(project: Path, command: str, session: str = "b1"):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "session_id": session, "cwd": str(project)}


def test_a_shell_command_naming_a_tracked_file_gets_its_pack_once(tmp_path, monkeypatch):
    calls = _fake_pack(monkeypatch)
    p = _project(tmp_path)
    out = hook.pre_edit(_bash(p, "sed -n 1,40p app.py && cat nowhere.py"))
    assert "`app.py`" in out["hookSpecificOutput"]["additionalContext"] and len(calls) == 1, "a file that does not exist costs no pack"
    assert hook.pre_edit(_bash(p, "cat app.py")) is None, "once per session"


def test_a_shell_command_gets_at_most_two_packs_and_ignores_other_commands(tmp_path, monkeypatch):
    _fake_pack(monkeypatch)
    p = _project(tmp_path)
    for name in ("b.py", "c.py", "d.py"):
        (p / name).write_text("x = 1\n")
    out = hook.pre_edit(_bash(p, "cat app.py b.py c.py d.py"))
    assert out["hookSpecificOutput"]["additionalContext"].count("devkb pack for") == hook.BASH_FILES
    assert hook.pre_edit(_bash(p, "git status && ls tests", session="b2")) is None
    assert hook.pre_edit(_bash(p, "cat /etc/hosts ../outside.py", session="b3")) is None
