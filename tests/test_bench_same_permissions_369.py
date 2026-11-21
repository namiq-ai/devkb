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
    prompt = pb.prompt_for("1", "T", "Body.", None)
    cmds = {a: pb.claude_cmd("1", a, prompt, "mcp.json") for a in sorted(pb.BASES) + sorted(pb.HIDE_LOCATION)}
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


def test_a_prompt_without_the_command_rules_is_refused():
    import pytest
    with pytest.raises(ValueError):
        pb.claude_cmd("1", "none", "a prompt someone stripped", "mcp.json")
    assert sb.COMMANDS.strip() in pb.claude_cmd("1", "none", pb.prompt_for("1", "T", "B", None), "mcp.json")[2]


def test_the_story_bench_prompt_carries_the_rules_too():
    src = (ROOT / "bench" / "policy" / "storybench.py").read_text()
    run = src[src.index("def run_one"):src.index("\ndef ", src.index("def run_one") + 5)]
    assert '"-p", story_prompt(t)' in run
    assert sb.COMMANDS.strip() in sb.story_prompt({"title": "T", "body": "B"})


def test_denial_reasons_groups_by_the_sessions_own_reason(tmp_path):
    import json
    sys.path.insert(0, str(ROOT / "bench" / "policy" / "probes"))
    import denial_reasons as dr
    cases = [("none", "cat > t.py <<'E'\nd = {\"a\": 1}\nE", "Contains brace with quote character (expansion obfuscation)",
              "code with braces and quotes in the command"),
             ("main", "ls ..", "This Bash command contains multiple operations. The following part requires approval: ls ..",
              "a path outside the checkout"),
             ("main", "sed -i 's/f(x)/g(\"y\")/' a.py", "sed command requires approval (contains potentially dangerous operations)", "sed -i"),
             ("main", "cd w; git status", "This command changes directory before running a version-control command", "cd, then git"),
             ("main", "R=$PWD; ls $R", "A variable in this command can't be checked before it runs", "a variable or an env-var prefix"),
             ("none", ".venv/bin/devkb build --project .", "Permission to use Bash with command .venv/bin/devkb build has been denied.",
              "devkb denied in a no-devkb arm"),
             ("main", "", "PreToolUse:Grep hook error: devkb answered this search from the graph (Complete)",
              "the guardrail answered instead (a hook deny, by design)")]
    for i, (arm, cmd, reason, want) in enumerate(cases):
        d = tmp_path / f"p1-{arm}-r{i}"
        d.mkdir()
        tool = "Grep" if not cmd else "Bash"
        ev = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": tool, "input": {"command": cmd}}]}},
              {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": reason}]}},
              {"type": "result", "permission_denials": [{"tool_name": tool, "tool_use_id": "t1", "tool_input": {"command": cmd}}]}]
        (d / "stream.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
        a, refused = dr.refusals(d / "stream.jsonl")
        assert [dr.group(a, c, r) for c, r in refused] == [want], want
