"""#383: `devkb build --allow-foreign-checkout` builds another checkout of this repository (both stages); without the
flag the build refuses it, as ODSF-104 requires."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _second_checkout(tmp_path: Path) -> Path:
    """A clone that shares this checkout's root commit, with one file checked out so the build stays quick."""
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("needs a git checkout of devkb")
    d = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", "--no-checkout", str(ROOT), str(d)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(d), "checkout", "-q", "HEAD", "--", "AGENTS.md"], check=True, capture_output=True)
    return d


def _build(d: Path, *flags: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore", HOME=str(d.parent))
    for k in ("DEVKB_DIR", "DEVKB_GUARDRAIL", "DEVKB_TELEMETRY"):
        env.pop(k, None)
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", ".", *flags], cwd=d, env=env,
                          capture_output=True, text=True, timeout=600)


def test_the_flag_the_refusal_names_builds_both_stages(tmp_path):
    d = _second_checkout(tmp_path)
    p = _build(d, "--allow-foreign-checkout")
    assert p.returncode == 0, p.stderr
    assert "unrecognized arguments" not in p.stderr
    assert (d / ".devkb" / "symbols-nodes.jsonl").exists() and (d / ".devkb" / "nodes.jsonl").exists()
    assert "--allow-foreign-checkout" in p.stderr            # the warning that another checkout's code ran


def test_without_the_flag_the_build_still_refuses(tmp_path):
    d = _second_checkout(tmp_path)
    p = _build(d)
    assert p.returncode != 0
    assert "pass --allow-foreign-checkout" in p.stderr
    assert not (d / ".devkb" / "nodes.jsonl").exists()
