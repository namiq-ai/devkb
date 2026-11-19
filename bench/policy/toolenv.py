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


def build(ref: str) -> dict:
    """{commit, src, bin, hook, hook_sha} for ref, built once and reused."""
    sha = resolve(ref)
    d = ENVS / sha[:12]
    info = d / "toolenv.json"
    if info.exists():
        return json.loads(info.read_text())
    src = d / "src"
    src.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(sb.REPO), "archive", sha], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(src)], input=tar, check=True)
    sb.sh(["uv", "venv", "-q", str(d / ".venv")])
    sb.sh(["uv", "pip", "install", "-q", "--python", str(d / ".venv" / "bin" / "python"), str(src), "libclang"])
    out = {"ref": ref, "commit": sha, "src": str(src), "bin": str(d / ".venv" / "bin" / "devkb"),
           "hook": str(src / "scripts" / "devkb_guardrail.py"), "post": str(src / "scripts" / "devkb_guardrail_post.py"),
           "hook_sha": hook_sha(src)}
    v = subprocess.run([str(d / ".venv" / "bin" / "python"), "-c", "import devkb, devkb.cli"], capture_output=True, text=True)
    if v.returncode:
        raise RuntimeError(f"toolenv {sha[:12]}: devkb does not run: {v.stderr[-300:]}")
    info.write_text(json.dumps(out, indent=2) + "\n")
    return out


def hooks_settings(env: dict) -> dict:
    """`.claude/settings.json` hooks that run the environment's own guardrail, not the checkout's copy."""
    def cmd(script: str) -> str:
        return f'python3 "{script}" 2>/dev/null || true'
    out = {"PreToolUse": [{"matcher": "Read|Grep|Bash", "hooks": [{"type": "command", "timeout": 20, "command": cmd(env["hook"])}]}]}
    if Path(env["post"]).exists():
        out["PostToolUse"] = [{"matcher": "Grep|Bash", "hooks": [{"type": "command", "timeout": 20, "command": cmd(env["post"])}]}]
    return out


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else "origin/main"), indent=2))
