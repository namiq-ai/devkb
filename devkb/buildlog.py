"""One build at a time, and a trace of every build (#158).

`logged_build(args)` is what `devkb build` runs. It takes `.devkb/build.lock` (an advisory lock the operating system drops
when the process dies, so a killed build never leaves a stale lock), runs the build, and appends one line to
`.devkb/build.log`:

    2026-11-20T10:15:02+0000 head=<40-hex> exit=0 took=3.2s [note]

`exit=0` is a graph at that HEAD; any other exit is a failed or killed build, and `note` carries the last line of its
error. `build --hook` (what the git hooks run) first waits for the lock, then skips the build when the graph is already
at HEAD, so a burst of checkouts costs one build, not one per checkout.
`last_failure(devkb_dir)` is what read commands use to say that the last build failed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # no advisory locks (Windows): builds run unserialised
    fcntl = None  # type: ignore[assignment]

LOG, LOCK = "build.log", "build.lock"


def _head(root: Path) -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def _manifest_head(devkb_dir: Path) -> str:
    try:
        return json.loads((devkb_dir / "manifest.json").read_text()).get("git_head", "")
    except (OSError, ValueError):
        return ""


def _append(devkb_dir: Path, head: str, code: int, took: float, note: str = "") -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} head={head or '?'} exit={code} took={took:.1f}s"
    if note:
        line += " " + note.replace("\n", " ")[:300]
    try:
        with open(devkb_dir / LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # a log that cannot be written must never turn a good build into a failure


def last_failure(devkb_dir: Path) -> str | None:
    """A sentence about the newest build.log line when that build failed, else None (no log, or the last build passed)."""
    try:
        lines = (devkb_dir / LOG).read_text().splitlines()
    except OSError:
        return None
    if not lines:
        return None
    m = re.search(r"head=(\S+) exit=(-?\d+)", lines[-1])
    if not m or m.group(2) == "0":
        return None
    return f"the last build failed (exit {m.group(2)} at {m.group(1)[:8]}); see {devkb_dir.name}/{LOG}"


def _project(args: list[str]) -> str | None:
    for i, a in enumerate(args):
        if a == "--project" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--project="):
            return a.split("=", 1)[1]
    return None


def logged_build(args: list[str]) -> int:
    hook = "--hook" in args
    args = [a for a in args if a != "--hook"]
    code = _project(args)
    try:
        from devkb.project_context import resolve  # noqa: PLC0415
        ctx = resolve(code) if code else None
    except Exception:  # not a project we can resolve: run the build as before and let it report the problem
        ctx = None
    if ctx is None:
        return _build(args)[0]
    devkb_dir, root = Path(ctx.devkb_dir), Path(ctx.repo_root)
    devkb_dir.mkdir(parents=True, exist_ok=True)
    with open(devkb_dir / LOCK, "a+") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)  # waits for a running build; the next one then sees what it left
        head = _head(root)
        if hook and head and _manifest_head(devkb_dir) == head:
            _append(devkb_dir, head, 0, 0.0, "up to date, skipped")
            return 0
        t0 = time.monotonic()
        rc, err = _build(args)
        _append(devkb_dir, _head(root), rc, time.monotonic() - t0, "" if rc == 0 else err)
        return rc


def _build(args: list[str]) -> tuple[int, str]:
    """Run `devkb build` in a child, so a crash or a kill is a result to log rather than the end of this process."""
    cmd = [sys.executable, "-P", "-m", "devkb.cli", "build-direct", *args]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).resolve().parent.parent), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    tail = [ln for ln in p.stderr.strip().splitlines() if ln.strip()]
    return p.returncode, (tail[-1] if tail else "")
