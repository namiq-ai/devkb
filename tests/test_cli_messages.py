"""#99: the devkb command prints a subcommand's error message instead of exiting silently."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from devkb import cli


def test_a_subcommand_error_message_reaches_stderr(tmp_path):
    """Through the real entry point, as a user runs it: `python -m devkb.cli init` outside a git repository."""
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run([sys.executable, "-m", "devkb.cli", "init", "--project", str(tmp_path), "--no-build"],
                       capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(root)})
    assert p.returncode == 1
    assert "is not a git repository" in p.stderr, (p.stdout, p.stderr)


def test_a_numeric_exit_code_still_passes_through_silently(monkeypatch, capsys):
    import runpy

    def fake(module, run_name, alter_sys):
        raise SystemExit(3)
    monkeypatch.setattr(runpy, "run_module", fake)
    assert cli._run("devkb.anything", []) == 3
    assert capsys.readouterr().err == ""
