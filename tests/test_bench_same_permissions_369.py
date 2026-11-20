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


def test_every_arm_gets_the_same_allow_rules_and_only_the_devkb_deny_differs():
    arms = sorted(pb.BASES)
    allows = {a: pb.permissions(a)[0] for a in arms}
    assert all(v == sb.ALLOW for v in allows.values())
    for a in arms:
        deny = pb.permissions(a)[1]
        assert deny == sb.DENY + (DEVKB_DENY if a in ("none", "nonekeep") else [])


def test_the_prompt_is_the_same_for_every_arm_and_carries_the_command_rules():
    prompt = pb.prompt_for("1", "T", "Body.", None)                # the prompt takes no arm: the same for all
    assert sb.COMMANDS.strip() in prompt and "{commands}" not in prompt
    story = pb.prompt_for("117", "T", "Body.", None)
    assert sb.COMMANDS.strip() in story
    for words in ("Write and Edit tools", ".venv/bin/python", "stay inside the checkout", "$(...)"):
        assert words in sb.COMMANDS


def test_the_run_uses_the_permissions_helper():
    src = (ROOT / "bench" / "policy" / "policybench.py").read_text()
    run = src[src.index("def _run_one"):src.index("def ", src.index("def _run_one") + 10)]
    assert "permissions(arm)" in run and "*sb.ALLOW" not in run
