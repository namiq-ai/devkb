"""shared helper for repros: build a fixture repo, run the guardrail hook on a search."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CK = Path(__file__).resolve().parents[2]
PY = str(CK / ".venv/bin/python")
COUNT = [0]


def fixture(files):
    d = Path(tempfile.mkdtemp(prefix="fx"))
    for n, t in files.items():
        (d / n).parent.mkdir(parents=True, exist_ok=True)
        (d / n).write_text(t)
    env = dict(os.environ, PYTHONPATH=str(CK))
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@b.c", "commit", "-q", "-m", "x"], cwd=d)
    r = subprocess.run([PY, "-m", "devkb.cli", "build", "--project", str(d)], capture_output=True, text=True, cwd=CK, env=env)
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit(2)
    return d


def hook(repo, tool, inp):
    COUNT[0] += 1
    home = tempfile.mkdtemp(prefix="hm")
    ev = dict(tool_name=tool, tool_input=inp, cwd=str(repo), session_id="s", tool_use_id="t%d" % COUNT[0])
    r = subprocess.run([PY, str(CK / "scripts/devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True,
                       env=dict(os.environ, HOME=home), cwd=CK)
    if not r.stdout.strip():
        return None, ""
    j = json.loads(r.stdout)["hookSpecificOutput"]
    return j.get("permissionDecision", "context"), j.get("permissionDecisionReason") or j.get("additionalContext")


def bash(repo, cmd):
    return hook(repo, "Bash", dict(command=cmd))


def grep(repo, cmd):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=repo).stdout
