"""ODSF-304: devkb finds every test function and every Odoo declaration, and
reports what share of a project the graph holds.

Each case builds a throwaway git repo, because discovery is `git ls-files`
and a fake file list would test nothing.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, coverage, test_discovery  # noqa: E402
from devkb.extractors import test_inventory  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    _git(tmp_path, "init", "-q")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(tmp_path, "add", "-A")
    return tmp_path


def _ctx(root: Path) -> ProjectContext:
    return ProjectContext(
        code="TST", repo_root=root, ticket_prefix="TST", issues_dir=root / "issues",
        tests_dir=root / "tests", sprint_dir=root / "historical" / "sprints",
        devkb_dir=root / ".devkb", board_file=root / "board.md", wp_map_file=root / "wp.json",
    )


def test_tests_are_found_wherever_they_live_and_vendored_ones_are_not(tmp_path):
    root = _repo(tmp_path, {
        "svc/tests/test_a.py": "def test_one():\n    pass\n\nclass TestX:\n    def test_two(self):\n        pass\n",
        "web/cart.test.js": "it('adds an item', () => {})\ntest.skip(\"removes it\", () => {})\n",
        "node_modules/dep/test_vendored.py": "def test_not_ours():\n    pass\n",
        "svc/app.py": "def run():\n    pass\n",
    })
    found = test_discovery.list_test_files(root)
    assert found == ["svc/tests/test_a.py", "web/cart.test.js"]
    assert [n for n, _ in test_discovery.tests_in_file(root, "svc/tests/test_a.py")] == ["test_one", "test_two"]
    assert [n for n, _ in test_discovery.tests_in_file(root, "web/cart.test.js")] == ["adds an item", "removes it"]


def test_a_broken_test_file_does_not_hide_the_rest(tmp_path):
    root = _repo(tmp_path, {"tests/test_bad.py": "def test_(:\n", "tests/test_ok.py": "def test_fine():\n    pass\n"})
    assert test_discovery.tests_in_file(root, "tests/test_bad.py") == []
    assert [n for n, _ in test_discovery.tests_in_file(root, "tests/test_ok.py")] == ["test_fine"]


def test_inventory_makes_a_testcase_per_function_linked_to_its_file(tmp_path):
    root = _repo(tmp_path, {"svc/tests/test_a.py": "def test_one():\n    pass\n\ndef test_two():\n    pass\n"})
    g = test_inventory.extract(_ctx(root))
    assert {n.natural_key for n in g.nodes("TestCase")} == {"svc/tests/test_a.py:1", "svc/tests/test_a.py:4"}
    assert {(e.src, e.dst) for e in g.edges("DEFINED_IN")} == {
        ("svc/tests/test_a.py:1", "svc/tests/test_a.py"), ("svc/tests/test_a.py:4", "svc/tests/test_a.py")}


def _decorator(src: str) -> ast.expr:
    return ast.parse(f"{src}\ndef f():\n    pass\n").body[0].decorator_list[0]


def test_odoo_routes_are_recognised_and_other_decorators_are_not():
    assert build_symbols._decorator_route(_decorator("@http.route('/a', methods=['POST'])")) == ("POST", "/a")
    assert build_symbols._decorator_route(_decorator("@http.route(['/b', '/c'], auth='user')")) == ("ANY", "/b")
    assert build_symbols._decorator_route(_decorator("@router.get('/d')")) == ("GET", "/d")
    assert build_symbols._odoo_route(_decorator("@other.route('/e')")) is None


def test_odoo_xml_declarations_become_symbols(tmp_path):
    xml = (
        '<odoo>\n<template id="page" name="P"><t t-name="inner"/></template>\n'
        '<record id="v1" model="ir.ui.view"><field name="x"/></record>\n'
        '<record id="act" model="ir.actions.act_window"/>\n<record id="plain" model="res.partner"/>\n'
        '<menuitem id="m1" name="M"/>\n</odoo>\n')
    root = _repo(tmp_path, {"addon/views/a.xml": xml})
    found = build_symbols._odoo_xml_symbols(root)["addon/views/a.xml"]
    assert {(d["qualified_name"], d["kind"]) for d in found} == {
        ("page", "qweb_template"), ("inner", "qweb_template"), ("v1", "view"), ("act", "action"), ("m1", "menu")}


def test_coverage_fails_a_category_below_its_floor_and_ignores_tiny_populations(tmp_path):
    tests = "".join(f"def test_{i}():\n    pass\n" for i in range(10))
    root = _repo(tmp_path, {"tests/test_many.py": tests, "docs/a.md": "# a\n"})
    ctx = _ctx(root)
    ctx.devkb_dir.mkdir()
    held = [{"type": "TestCase", "natural_key": f"tests/test_many.py:{1 + 2 * i}"} for i in range(5)]
    (ctx.devkb_dir / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in held) + "\n")
    rows = {r["category"]: r for r in coverage.measure(ctx)}
    assert (rows["test_functions"]["covered"], rows["test_functions"]["population"]) == (5, 10)
    assert rows["test_functions"]["ok"] is False
    assert rows["spec_documents"]["enforced"] is False and rows["spec_documents"]["ok"] is True
