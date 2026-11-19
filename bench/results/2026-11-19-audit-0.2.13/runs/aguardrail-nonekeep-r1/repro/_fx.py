"""Shared fixture helpers for the audit reproductions: a throwaway git repository with a built graph, and the
guardrail hook run on it with a private HOME (nothing outside this checkout or a temp directory is touched)."""
import json, os, subprocess, sys, tempfile, itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
HOOK = ROOT / "scripts" / "devkb_guardrail.py"
_n = itertools.count()


def _env(home):
    e = dict(os.environ, HOME=str(home), PYTHONPATH=str(ROOT), DEVKB_GUARDRAIL="1", PYTHONWARNINGS="ignore")
    e.pop("DEVKB_GUARDRAIL_TEACH", None)
    return e


def fixture(files: dict) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="devkb-audit-"))
    repo = tmp / "repo"
    repo.mkdir()
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    run = lambda *a: subprocess.run(a, cwd=repo, capture_output=True, text=True, check=True,
                                    env=dict(os.environ, GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@e.x",
                                             GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@e.x"))
    run("git", "init", "-q")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "x")
    subprocess.run([str(PY), "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, env=_env(tmp / "home"),
                   capture_output=True, text=True, check=True)
    return repo


def hook(repo: Path, tool: str, inp, cwd=None, env_extra=None):
    """(kind, text): kind is 'deny', 'along' or 'none' (a reminder counts as none)."""
    home = repo.parent / "home"
    inp = {"command": inp} if isinstance(inp, str) else inp
    n = next(_n)
    ev = {"tool_name": tool, "tool_input": inp, "cwd": str(cwd or repo), "session_id": f"s{os.getpid()}-{n}",
          "tool_use_id": f"t{os.getpid()}-{n}"}
    env = _env(home)
    env.update(env_extra or {})
    p = subprocess.run([str(PY), "-P", str(HOOK)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=repo)
    if not p.stdout.strip():
        return "none", ""
    h = json.loads(p.stdout)["hookSpecificOutput"]
    text = h.get("permissionDecisionReason") or h.get("additionalContext", "")
    if text.startswith("devkb guardrail:"):
        return "none", text
    return ("deny" if h.get("permissionDecision") == "deny" else "along"), text


def grep(repo: Path, cmd: str, cwd=None) -> str:
    return subprocess.run(cmd, shell=True, cwd=cwd or repo, capture_output=True, text=True).stdout
