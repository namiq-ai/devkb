"""Shared helpers for the audit reproductions: build a throw-away git repo, build its devkb graph, run the guardrail."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def env(home: str, **extra) -> dict:
    e = dict(os.environ, HOME=home, DEVKB_TELEMETRY="0", DEVKB_GUARDRAIL="1", PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    e.pop("DEVKB_GUARDRAIL_TEACH", None)
    e.pop("DEVKB_MISSLOG", None)
    e.update(extra)
    return e


def sh(*cmd, cwd, home="/nonexistent", check=True):
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, env=env(home))
    if check and p.returncode:
        raise SystemExit(f"command failed: {cmd}\n{p.stdout}\n{p.stderr}")
    return p


def make_repo(files: dict, build=True, commit=True) -> tuple[Path, str]:
    """(repo dir, home dir). `files` maps a relative path to its text."""
    tmp = Path(tempfile.mkdtemp(prefix="devkb-audit-"))
    repo, home = tmp / "repo", tmp / "home"
    repo.mkdir()
    home.mkdir()
    for rel, text in files.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    sh("git", "init", "-q", cwd=repo)
    sh("git", "-c", "user.email=a@b.c", "-c", "user.name=a", "add", "-A", cwd=repo)
    if commit:
        sh("git", "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init", cwd=repo)
    if build:
        sh(PY, "-m", "devkb.cli", "build", "--project", ".", cwd=repo, home=str(home))
    return repo, str(home)


def guard(repo: Path, home: str, tool: str, inp: dict, sid: str = "s1", **extra) -> tuple[str, str]:
    """(decision, text): decision is deny, ctx (added context) or none."""
    ev = {"tool_name": tool, "tool_input": inp, "cwd": str(repo), "session_id": sid, "tool_use_id": sid + "-" + str(os.getpid())}
    p = subprocess.run([PY, str(ROOT / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True,
                       cwd=repo, env=env(home, **extra))
    if not p.stdout.strip():
        return "none", ""
    d = json.loads(p.stdout)["hookSpecificOutput"]
    return d.get("permissionDecision", "ctx"), d.get("permissionDecisionReason") or d.get("additionalContext") or ""


def grep_out(repo: Path, cmd: str) -> list[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=repo).stdout.splitlines()


def lines_of(text: str) -> list[str]:
    import re
    return [re.sub(r"^(\S+?:\d+:)\s+", r"\1", l) for l in text.splitlines() if re.match(r"[\w./-]+:\d+:|^\d+:", l)]
