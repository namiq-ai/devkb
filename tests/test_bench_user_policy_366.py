"""#366: the user-facing arms hold what `devkb init` writes (or the short candidate), and the inject arm puts the pack of
the ticket's code file in front of the prompt."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sys.path.insert(0, str(ROOT))
import policybench as pb  # noqa: E402
import release_table as rt  # noqa: E402
from devkb import init  # noqa: E402


def test_userpolicy_is_what_devkb_init_writes(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    init.run(tmp_path, "cli", hooks=False, dry_run=False)
    agents, claude = pb.user_policy({"src": str(ROOT)}, "full")
    assert agents == (tmp_path / "AGENTS.md").read_text()
    assert claude == (tmp_path / "CLAUDE.md").read_text()
    assert "Developing devkb" not in agents                 # this repository's own process text is not a user's


def test_short_is_shorter_and_names_the_commands():
    full, _ = pb.user_policy({"src": str(ROOT)}, "full")
    short, claude = pb.user_policy({"src": str(ROOT)}, "short")
    assert len(short) < len(full) / 3 and claude.strip().splitlines()[1] == "@AGENTS.md"
    assert all(c in short for c in ("devkb symbol", "devkb uses", "devkb pack --project . file", "refactor"))


def test_the_arms_run_mains_devkb_and_are_in_the_table():
    for a in ("userpolicy", "short", "inject"):
        assert a in pb.BASES and a in pb.ENV_REF and pb.ARM_ENV[a] == pb.ARM_ENV["main"] and a in pb.USER_POLICY
        assert a in rt.ORDER and a not in rt.NONE


def test_write_user_policy_replaces_the_checkouts_files(tmp_path):
    (tmp_path / "AGENTS.md").write_text("## Developing devkb\nprocess\n")
    pb.write_user_policy(tmp_path, {"src": str(ROOT)}, "short")
    assert (tmp_path / "AGENTS.md").read_text() == pb.user_policy({"src": str(ROOT)}, "short")[0]


def test_inject_gives_the_pack_of_the_first_code_file(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "core.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_core.py").write_text("x = 1\n")
    body = "**Where to start:** `tests/test_core.py` and `pkg/core.py`.\n"
    monkeypatch.setattr(pb, "ticket_for", lambda issue: {"title": "t", "body": body})
    fake = tmp_path / "devkb"
    fake.write_text("#!/bin/sh\necho \"PACK $*\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    text = pb.injected_context("1", tmp_path, str(fake))
    assert text.startswith("Before this session, devkb ran `devkb pack --project . file pkg/core.py`")
    assert "PACK pack --project . file pkg/core.py" in text      # the checkout's path shown as `.`
    monkeypatch.setattr(pb, "ticket_for", lambda issue: {"title": "t", "body": "No location."})
    assert pb.injected_context("1", tmp_path, str(fake)) == ""
