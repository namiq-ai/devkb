from __future__ import annotations
# Hidden acceptance for #50 (from b3272e6).
"""Audit 0.2.5 -> 0.2.8: `devkb init` never removes or rewrites text it does not own (#50, #51, #52)."""




import re
import subprocess


import sys


from pathlib import Path


import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from devkb import init  # noqa: E402


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _refusal(root, toolset, capsys):
    """Run init; return the refusal text (exception or printed output), whatever form the refusal takes."""
    msg = ""
    try:
        init.run(root, toolset, hooks=False, dry_run=False)
    except BaseException as e:  # noqa: BLE001 - any refusal form is accepted
        msg = str(e)
    out = capsys.readouterr()
    return msg + out.out + out.err


def test_an_orphan_begin_marker_makes_init_refuse_and_leaves_the_file_byte_identical(tmp_path, capsys):  # #50
    root = _repo(tmp_path)
    original = ("# Team\n" + init.BEGIN + "\nold block, end marker deleted by hand\n\n"
                "## IMPORTANT USER SECTION\nkeep me\n").encode()
    (root / "AGENTS.md").write_bytes(original)
    for toolset in ("lean-pack", "lean-pack", None):
        text = _refusal(root, toolset, capsys)
        assert "AGENTS.md" in text and re.search(r"\b2\b", text), text
        assert (root / "AGENTS.md").read_bytes() == original
    assert not (root / "CLAUDE.md").exists(), "a refusal writes nothing at all"


def test_an_orphan_end_marker_is_refused_too(tmp_path, capsys):  # #50
    root = _repo(tmp_path)
    original = b"# Rules\n\nkeep me\n<!-- devkb:end -->\n"
    (root / "CLAUDE.md").write_bytes(original)
    text = _refusal(root, "lean-pack", capsys)
    assert "CLAUDE.md" in text and re.search(r"\b4\b", text), text
    assert (root / "CLAUDE.md").read_bytes() == original
