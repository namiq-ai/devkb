"""The Claude Code plugin in plugins/devkb: its skills are copies of skills/, its server uses the default toolset, and
the package version it installs exists."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "devkb"


def test_plugin_skills_are_identical_to_the_originals():
    for skill in (PLUGIN / "skills").glob("*/SKILL.md"):
        assert skill.read_text() == (ROOT / "skills" / skill.parent.name / "SKILL.md").read_text(), skill.parent.name


def test_plugin_server_uses_lean_pack_and_a_released_version():
    args = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["devkb"]["args"]
    assert args[-1] == "lean-pack" and "${CLAUDE_PROJECT_DIR}" in args
    floor = re.search(r">=([0-9.]+)", args[1]).group(1)
    version = re.search(r'^version = "([0-9.]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert tuple(map(int, floor.split("."))) <= tuple(map(int, version.split(".")))
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"] == version


def test_marketplace_points_at_the_plugin():
    m = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in m["plugins"] if p["name"] == "devkb")
    assert (ROOT / entry["source"]).resolve() == PLUGIN.resolve()
