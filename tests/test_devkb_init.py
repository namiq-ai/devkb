"""`devkb init`: managed blocks only, idempotent, and fully reversible."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkb import init  # noqa: E402

ORIGINAL = {
    "AGENTS.md": "# Agents\n\nUse ruff.\n",
    "CLAUDE.md": "# Project rules\n\nNever push to main.\n",
    ".gitignore": "node_modules/\n",
    ".mcp.json": json.dumps({"mcpServers": {"other": {"command": "x"}}}, indent=2) + "\n",
}


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        (tmp_path / rel).write_text(text)
    return tmp_path


def test_init_adds_blocks_keeps_the_repository_s_content_and_is_idempotent(tmp_path):
    root = _repo(tmp_path, ORIGINAL)
    changes = init.run(root, "lean", hooks=False, dry_run=False)
    assert sorted(changes) == ["update .gitignore", "update .mcp.json", "update AGENTS.md", "update CLAUDE.md"]
    agents = (root / "AGENTS.md").read_text()
    assert agents.startswith("# Agents\n\nUse ruff.\n") and "devkb pack --project . file PATH" in agents and "**Complete**" in agents
    assert (root / "CLAUDE.md").read_text().startswith("# Project rules") and "@AGENTS.md" in (root / "CLAUDE.md").read_text()
    servers = json.loads((root / ".mcp.json").read_text())["mcpServers"]
    assert servers["other"] == {"command": "x"} and servers["devkb"]["args"] == ["mcp", "--project", ".", "--toolset", "lean"]
    assert ".devkb/" in (root / ".gitignore").read_text()
    assert init.run(root, "lean", hooks=False, dry_run=False) == [], "a second run changes nothing"


def test_remove_restores_every_file_exactly(tmp_path):
    root = _repo(tmp_path, ORIGINAL)
    init.run(root, "lean", hooks=True, dry_run=False)
    init.run(root, None, hooks=False, dry_run=False)
    for rel, text in ORIGINAL.items():
        assert (root / rel).read_text() == text, rel
    assert not (root / ".git/hooks/post-commit").exists()


def test_a_bare_repository_gets_new_files_and_loses_them_again(tmp_path):
    root = _repo(tmp_path, {})
    init.run(root, "lean", hooks=True, dry_run=False)
    hook = root / ".git/hooks/post-commit"
    assert hook.read_text().startswith("#!/bin/sh\n") and "devkb build" in hook.read_text() and hook.stat().st_mode & 0o111
    init.run(root, None, hooks=False, dry_run=False)
    assert not any((root / rel).exists() for rel in ("AGENTS.md", "CLAUDE.md", ".gitignore", ".mcp.json"))


def test_dry_run_writes_nothing(tmp_path):
    root = _repo(tmp_path, ORIGINAL)
    assert init.run(root, "lean", hooks=False, dry_run=True)
    assert all((root / rel).read_text() == text for rel, text in ORIGINAL.items())


def test_the_default_gives_agents_lean_pack_and_instructions_naming_only_its_tools(tmp_path):
    import re as _re
    from devkb.mcp_server import TOOLSETS
    root = _repo(tmp_path, {})
    assert init.main(["--project", str(root), "--no-build"]) == 0
    assert json.loads((root / ".mcp.json").read_text())["mcpServers"]["devkb"]["args"][-1] == "lean-pack"
    agents = (root / "AGENTS.md").read_text()
    named = set(_re.findall(r"`([a-z_]+)`", agents)) & set(TOOLSETS["all"])
    assert named and named <= set(TOOLSETS["lean-pack"]), named - set(TOOLSETS["lean-pack"])
    assert 'pack(kind="change"' in agents and "search with grep" in agents, "the measured rule: packs for chains, grep for one hop"


def test_the_file_pack_lists_what_depends_on_a_file_and_the_tests_reaching_it(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_devkb_coverage_classes_odsf313 import _api  # noqa: PLC0415
    from devkb.packs import Packer  # noqa: PLC0415
    text = Packer(_api(tmp_path, monkeypatch)).file("app/store.py")
    assert "## Functions other files call (2 of 3)" in text and "`RuntimeStore.add_edge` — 2 file(s): `app/routes.py:6" in text
    assert "`app/routes.py`" in text and "tests/test_store.py" in text
    assert "The graph has no code" in Packer(_api(tmp_path / "x", monkeypatch)).file("nowhere.py")


def test_init_warns_when_agents_could_not_start_the_devkb_command(monkeypatch, capsys):
    import shutil
    import sys as _sys
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert "not on your PATH" in init.server_command_problem()
    venv = Path(_sys.prefix)
    monkeypatch.setattr(shutil, "which", lambda name: str(venv / "bin" / "devkb"))
    monkeypatch.setattr(_sys, "base_prefix", "/usr")
    assert "only on the PATH of this virtual environment" in init.server_command_problem()
    monkeypatch.setattr(shutil, "which", lambda name: "/home/u/.local/bin/devkb")
    assert init.server_command_problem() is None
