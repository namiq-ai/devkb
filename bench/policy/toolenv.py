"""A devkb tool environment built from one exact commit, for a benchmark arm (#225).

  python toolenv.py REF        build (or reuse) the environment for REF and print its directory

`build(ref)` unpacks the commit with `git archive` into `toolenvs/<sha12>/src`, makes a virtual environment beside it
and installs that tree, so an arm's `devkb` command, its graph build and its hook script all come from the same commit,
and the agent editing the checkout cannot change the devkb that helps it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import storybench as sb

ENVS = sb.B / "toolenvs"


def resolve(ref: str) -> str:
    return sb.sh(["git", "-C", str(sb.REPO), "rev-parse", f"{ref}^{{commit}}"]).stdout.strip()


def latest_release(ref: str = "origin/main") -> str:
    """The newest release tag reachable from ref (`v0.2.12` while 0.2.13 is being built)."""
    return sb.sh(["git", "-C", str(sb.REPO), "describe", "--tags", "--abbrev=0", "--match", "v*", ref]).stdout.strip()


def hook_sha(src: Path) -> str:
    return hashlib.sha256((src / "scripts" / "devkb_guardrail.py").read_bytes()).hexdigest()[:16]


_LOCK = __import__("threading").Lock()


class held:
    """A lock held across threads and processes (a benchmark started while another runs shares templates and tool
    environments with it): a thread lock, then an exclusive flock on PATH."""
    _threads: dict = {}
    _guard = __import__("threading").Lock()

    def __init__(self, path):
        self.path = Path(path)
        with held._guard:
            self.tl = held._threads.setdefault(str(self.path), __import__("threading").Lock())

    def __enter__(self):
        import fcntl
        self.tl.acquire()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        self.tl.release()


def build(ref: str) -> dict:
    """{commit, src, bin, hook, hook_sha} for ref, built once and reused; one build at a time, so two runs that need the
    same new commit never install into the same directory together."""
    with held(ENVS / f".{resolve(ref)[:12]}.lock"):
        return _build(ref)


def _build(ref: str) -> dict:
    sha = resolve(ref)
    d = ENVS / sha[:12]
    info = d / "toolenv.json"
    if info.exists():
        return json.loads(info.read_text())
    if d.exists():                                # a build that died half way: start again
        import shutil
        shutil.rmtree(d)
    src = d / "src"
    src.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(sb.REPO), "archive", sha], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(src)], input=tar, check=True)
    sb.sh(["uv", "venv", "-q", str(d / ".venv")])
    sb.sh(["uv", "pip", "install", "-q", "--python", str(d / ".venv" / "bin" / "python"), f"{src}[mcp]", "libclang"])
    out = {"ref": ref, "commit": sha, "src": str(src), "bin": str(d / ".venv" / "bin" / "devkb"),
           "hook": str(src / "scripts" / "devkb_guardrail.py"), "post": str(src / "scripts" / "devkb_guardrail_post.py"),
           "hook_sha": hook_sha(src)}
    v = subprocess.run([str(d / ".venv" / "bin" / "python"), "-c", "import devkb, devkb.cli"], capture_output=True, text=True)
    if v.returncode:
        raise RuntimeError(f"toolenv {sha[:12]}: devkb does not run: {v.stderr[-300:]}")
    info.write_text(json.dumps(out, indent=2) + "\n")
    return out


def hooks_settings(env: dict, router: bool = False, context: bool = False) -> dict:
    """`.claude/settings.json` hooks that run the environment's own guardrail, not the checkout's copy. With `router`, also
    the environment's own prompt router (`devkb hook prompt`, docs/specs/workflow-router.md): the one difference between
    the rmain and router arms. With `context`, the silent `devkb hook context` that only records the task for `symbol`'s
    ranking (the ctx arm): the same hook slot as the router, nothing pushed."""
    def cmd(script: str) -> str:
        return f'python3 "{script}" 2>/dev/null || true'
    out = {"PreToolUse": [{"matcher": "Read|Grep|Bash", "hooks": [{"type": "command", "timeout": 20, "command": cmd(env["hook"])}]}]}
    if Path(env["post"]).exists():
        out["PostToolUse"] = [{"matcher": "Grep|Bash", "hooks": [{"type": "command", "timeout": 20, "command": cmd(env["post"])}]}]
    if router:
        out["UserPromptSubmit"] = [{"hooks": [{"type": "command", "timeout": 20, "command": f'"{env["bin"]}" hook prompt 2>/dev/null || true'}]}]
    if context and not router:
        out["UserPromptSubmit"] = [{"hooks": [{"type": "command", "timeout": 20, "command": f'"{env["bin"]}" hook context 2>/dev/null || true'}]}]
    return out


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else "origin/main"), indent=2))
