"""Shared fixture helpers for the audit repros: a throwaway git repo with a built devkb graph, and the hook runner."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / "scripts" / "devkb_guardrail.py"


def make_repo(files: dict, commit=True) -> Path:
    root = Path(tempfile.mkdtemp()) / "r"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if commit:
        for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
            subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    build(root)
    return root


def build(root):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                   check=True, capture_output=True)


def hook(root, tool_input, tool="Bash", home=None, first="ls", nth=[0]):
    """Run the hook on one search (after a warm-up `ls` so the once-per-session reminder is used up). Returns
    (decision, text)."""
    nth[0] += 1
    home = home or tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env["HOME"] = str(home)
    out = ""
    evs = [{"tool_name": "Bash", "tool_input": {"command": first}}] if first else []
    evs.append({"tool_name": tool, "tool_input": tool_input})
    for j, e in enumerate(evs):
        e.update(cwd=str(root), session_id=f"sa{nth[0]}", tool_use_id=f"ta{nth[0]}-{j}")
        out = subprocess.run([str(ROOT / ".venv/bin/python"), str(PRE)], input=json.dumps(e), capture_output=True, text=True,
                             env=env).stdout
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    return h.get("permissionDecision"), (h.get("permissionDecisionReason") or h.get("additionalContext") or "")


def grep_lines(root, cmd):
    return subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True).stdout.splitlines()
