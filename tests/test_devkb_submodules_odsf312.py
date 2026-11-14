"""ODSF-312: code in a checked-out git submodule is part of the product (OCO's oco-edge), so the graph indexes it."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, test_discovery  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
                   cwd=cwd, check=True, capture_output=True)


def test_python_and_tests_inside_a_submodule_are_listed(tmp_path):
    edge = tmp_path / "edge"
    (edge / "agent").mkdir(parents=True)
    (edge / "agent" / "probe.py").write_text("def probe():\n    return 1\n")
    (edge / "tests").mkdir()
    (edge / "tests" / "test_probe.py").write_text("def test_probe():\n    assert True\n")
    _git(edge, "init", "-q")
    _git(edge, "add", "-A")
    _git(edge, "commit", "-q", "-m", "edge")
    product = tmp_path / "product"
    product.mkdir()
    (product / "app.py").write_text("def main():\n    pass\n")
    _git(product, "init", "-q")
    _git(product, "add", "-A")
    _git(product, "submodule", "add", "-q", str(edge), "oco-edge")
    _git(product, "commit", "-q", "-m", "product")
    files = build_symbols._list_python_files(product)
    assert {"app.py", "oco-edge/agent/probe.py", "oco-edge/tests/test_probe.py"} <= set(files)
    assert "oco-edge/tests/test_probe.py" in test_discovery.list_test_files(product)
