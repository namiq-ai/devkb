"""Every file that carries the release version says the same one (docs/RELEASING.md: keep CITATION.cff in step with pyproject.toml at each release; the plugin
manifest and the hook that starts devkb through uvx name it too). 0.2.15 shipped with CITATION.cff still at 0.2.14 until this test was written."""
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_version():
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_citation_the_plugin_and_the_hook_name_the_projects_version():
    v = project_version()
    cff = re.search(r"^version:\s*(\S+)", (ROOT / "CITATION.cff").read_text(), re.M).group(1)
    plugin = json.loads((ROOT / "plugins" / "devkb" / ".claude-plugin" / "plugin.json").read_text())["version"]
    hook = re.search(r"devkb\[mcp\]>=([\d.]+)", (ROOT / "plugins" / "devkb" / "hooks" / "prompt.sh").read_text()).group(1)
    assert {"CITATION.cff": cff, "plugin.json": plugin, "prompt.sh": hook} == {"CITATION.cff": v, "plugin.json": v, "prompt.sh": v}


def test_the_citation_date_is_a_date_not_before_the_previous_release():
    m = re.search(r"^date-released:\s*(\d{4}-\d{2}-\d{2})", (ROOT / "CITATION.cff").read_text(), re.M)
    assert m and m.group(1) >= "2026-11-20", "date-released must be set to the release's date"
