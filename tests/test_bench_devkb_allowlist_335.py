"""#335: a devkb-arm agent may run every devkb command the checkout's policy tells it to run; the no-devkb arm may run none."""
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")


def covers(patterns, command):
    for p in patterns:
        m = re.fullmatch(r"Bash\((.*?)(:\*|\s\*|)\)", p)
        if m and command.startswith(m.group(1)):
            return True
    return False


def test_allow_covers_both_ways_to_call_devkb():
    assert covers(sb.ALLOW, "devkb pack --project . file x.py") and covers(sb.ALLOW, ".venv/bin/devkb pack --project . file x.py")


def test_every_devkb_command_in_the_policy_file_is_allowed():
    """The commands AGENTS.md tells an agent to run (in backticks, starting `devkb ` or `.venv/bin/devkb `) are matched by ALLOW.
    The no-devkb benchmark arm deletes the policy file; there is nothing to check there (and a failing test would make that arm's
    base suite red, which refuses every one of its runs)."""
    if not (HERE / "AGENTS.md").exists():
        pytest.skip("this checkout has no policy file (the no-devkb arm)")
    text = (HERE / "AGENTS.md").read_text()
    cmds = {m.group(1) for m in re.finditer(r"`((?:\.venv/bin/)?devkb (?:symbol|uses|outline|pack|docs|misses|build)[^`]*)`", text)}
    assert cmds, "the policy file names no devkb command: the test would pass for nothing"
    assert [c for c in cmds if not covers(sb.ALLOW, c)] == []
    if ".venv/bin/devkb" in text:                       # the checkout's own devkb, named without a subcommand in rule 1
        assert covers(sb.ALLOW, ".venv/bin/devkb pack --project . file x.py")


def _lists(tmp_path, monkeypatch, arm):
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "template_for", lambda a: tmp_path / "t")
    monkeypatch.setattr(pb, "from_template", lambda t, w: (Path(w).mkdir(parents=True), (Path(w) / ".bench-arm.json").write_text("{}")))
    monkeypatch.setattr(pb.toolenv, "build", lambda ref: {"bin": str(tmp_path / "devkb"), "commit": "x", "hook_sha": "x"})
    monkeypatch.setattr(pb, "score_run", lambda *a, **k: None)
    real = sb.sh
    monkeypatch.setattr(sb, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else real(cmd, **kw))
    got = {}
    real_run = subprocess.run
    monkeypatch.setattr(pb.subprocess, "run", lambda cmd, **k: (got.update(cmd=cmd), subprocess.CompletedProcess(cmd, 0))[1]
                        if cmd[0] == "claude" else real_run(cmd, **k))      # only the agent launch is stubbed (git calls are real)
    pb._run_one("9", arm, 1)
    cmd = got["cmd"]

    def after(flag):
        i = cmd.index(flag)
        out = []
        for x in cmd[i + 1:]:
            if x.startswith("--"):
                break
            out.append(x)
        return out
    return after("--allowedTools"), after("--disallowedTools")


def test_the_none_arm_denies_both_forms_and_the_devkb_arm_denies_neither(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    allow, deny = _lists(tmp_path / "a", monkeypatch, "none")
    for c in ("devkb pack --project . file x.py", ".venv/bin/devkb pack --project . file x.py"):
        assert covers(deny, c)
    (tmp_path / "b").mkdir()
    allow, deny = _lists(tmp_path / "b", monkeypatch, "main")
    for c in ("devkb pack --project . file x.py", ".venv/bin/devkb pack --project . file x.py"):
        assert covers(allow, c) and not covers(deny, c)
