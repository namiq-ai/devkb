"""The module-runs walk is skipped for a file that cannot hold a result (0.2.15 release check: it cost a Python build +20%)."""
import ast

from devkb import build_symbols as b

FILES = {
    "none": "def f(x):\n    return x + 1\n",
    "runpy": "import runpy\ndef g():\n    runpy.run_module('pkg.mod')\n",
    "dash_m": "import sys\ndef h():\n    return [sys.executable, '-m', 'pkg.other']\n",
    "helper": "import sys\ndef _run(m):\n    return [sys.executable, '-m', m]\ndef k():\n    _run('pkg.third')\n",
    "git": "def c():\n    return ['git', 'commit', '-m', 'msg']\n",
}


def test_the_prefilter_never_changes_a_result():
    for name, text in FILES.items():
        tree = ast.parse(text)
        assert b._safe_module_runs(tree, text) == b._safe_module_runs(tree), name


def test_a_file_without_a_marker_is_not_walked(monkeypatch):
    def boom(_tree):
        raise AssertionError("walked")
    monkeypatch.setattr(b, "_module_runs", boom)
    assert b._safe_module_runs(ast.parse(FILES["none"]), FILES["none"]) == []
