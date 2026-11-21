"""#369: every arm gets the same allow rules and the same prompt, and the prompt says how to run commands so the
benchmark's permission settings do not refuse them."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import policybench as pb  # noqa: E402
import storybench as sb  # noqa: E402

DEVKB_DENY = ["Bash(devkb:*)", "Bash(.venv/bin/devkb:*)"]


def test_every_arm_gets_the_same_command_and_only_the_devkb_deny_differs():
    def flags(cmd, name):
        i = cmd.index(name)
        out = []
        for a in cmd[i + 1:]:
            if a.startswith("--"):
                break
            out.append(a)
        return out
    cmds = {a: pb.claude_cmd("1", a, "PROMPT", "mcp.json") for a in sorted(pb.BASES) + sorted(pb.HIDE_LOCATION)}
    base = cmds["main"]
    for a, cmd in cmds.items():                               # the command a run starts, built for every arm
        assert flags(cmd, "--allowedTools") == sb.ALLOW, a
        deny = flags(cmd, "--disallowedTools")
        assert deny == sb.DENY + (DEVKB_DENY if pb.split_arm(a)[0] in ("none", "nonekeep") else []), a
        strip = lambda c: [x for x in c if x not in DEVKB_DENY]
        assert strip(cmd) == strip(base), a                   # nothing else differs


def test_the_prompt_is_the_same_for_every_arm_and_carries_the_command_rules():
    prompt = pb.prompt_for("1", "T", "Body.", None)                # the prompt takes no arm: the same for all
    assert sb.COMMANDS.strip() in prompt and "{commands}" not in prompt
    story = pb.prompt_for("117", "T", "Body.", None)
    assert sb.COMMANDS.strip() in story
    for words in ("Write and Edit tools", ".venv/bin/python", "stay inside the checkout", "$(...)"):
        assert words in sb.COMMANDS


def test_the_run_starts_the_command_claude_cmd_builds():
    src = (ROOT / "bench" / "policy" / "policybench.py").read_text()
    run = src[src.index("def _run_one"):src.index("\ndef ", src.index("def _run_one") + 10)]
    assert "claude_cmd(issue, arm, prompt, mcp)" in run and "--allowedTools" not in run
