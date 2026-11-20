"""#382: a test that binds a module to a short alias (`sb = importlib.import_module("storybench")`, or
`spec_from_file_location` + `module_from_spec`) is among the module's tests to run; a test that names a script by
path is listed as such; a load by a computed name says the list may be incomplete."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import process_api  # noqa: E402
from devkb.build_symbols import _dynamic_imports, literal_paths, unfollowed_loads  # noqa: E402
from devkb.packs import Packer  # noqa: E402

INSERT = "import importlib\nimport importlib.util\nimport os\nimport subprocess\nimport sys\nfrom pathlib import Path\n\n" \
         "HERE = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(HERE / \"tools\"))\n"
FILES = {
    "tools/storyline.py": "def count_turns(rows):\n    return len(rows)\n",
    "tools/gatekeep.py": "def decide(x):\n    return x > 1\n",
    "tools/runme.py": "def main():\n    print('ok')\n\n\nif __name__ == '__main__':\n    main()\n",
    "tools/dynamo.py": "def spin():\n    return 3\n",
    "lib/plain.py": "def plain():\n    return 1\n",
    "tests/test_alias.py": INSERT + "sl = importlib.import_module(\"storyline\")\n\n\n"
                                    "def test_count():\n    assert sl.count_turns([1]) == 1\n",
    "tests/test_spec.py": INSERT + "spec = importlib.util.spec_from_file_location(\"gk_mod\", HERE / \"tools\" / \"gatekeep.py\")\n"
                                   "gk = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(gk)\n\n\n"
                                   "def test_decide():\n    assert gk.decide(2)\n",
    "tests/test_run.py": INSERT + "SCRIPT = HERE / \"tools\" / \"runme.py\"\n\n\n"
                                  "def test_runs():\n    subprocess.run([sys.executable, str(SCRIPT)], check=True)\n",
    "tests/test_dyn.py": INSERT + "dm = importlib.import_module(os.environ.get(\"DYN\", \"dyn\" + \"amo\"))\n\n\n"
                                  "def test_spin():\n    assert dm.spin() == 3\n",
}


def _packer(root: Path) -> Packer:
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return Packer(process_api.ProcessAPI(str(root), telemetry=False))


def _tests(text: str) -> str:
    return text.split("## Tests that exercise it", 1)[1].split("\n## ", 1)[0]


def test_an_aliased_import_module_and_spec_load_are_followed(tmp_path):
    p = _packer(tmp_path)
    assert "`tests/test_alias.py`" in _tests(p.file("tools/storyline.py"))
    assert "`tests/test_spec.py`" in _tests(p.file("tools/gatekeep.py"))
    assert "tests/test_alias.py" in p.change("count_turns")       # the change pack sees the same call


def test_a_test_that_runs_a_script_by_path_is_listed_and_run(tmp_path):
    text = _packer(tmp_path).file("tools/runme.py")
    tests = _tests(text)
    assert "`tests/test_run.py` — names it by path: `tests/test_run.py:10:" in tests
    assert "Run: `" in text and "tests/test_run.py" in text.split("Run: `", 1)[1].split("`", 1)[0]


def test_a_load_by_a_computed_name_says_the_list_may_be_incomplete(tmp_path):
    p = _packer(tmp_path)
    tests = _tests(p.file("tools/dynamo.py"))
    assert "may be incomplete" in tests and "tests/test_dyn.py:10" in tests
    assert "may be incomplete" not in _tests(p.file("lib/plain.py"))   # not a directory the test puts on sys.path


def test_the_parsers_follow_only_literals():
    t = ast.parse("import importlib, importlib.util as u\nfrom importlib import import_module\n"
                  "a = importlib.import_module('pkg.mod')\nb = import_module('other')\nc = importlib.import_module(name)\n"
                  "d = importlib.import_module('.rel', 'pkg')\n"
                  "s = u.spec_from_file_location('x', ROOT / '..' / 'bench' / 'x.py')\nm = u.module_from_spec(s)\n"
                  "s = u.spec_from_file_location('y', BENCH / f'{n}.py')\nn2 = u.module_from_spec(s)\n")
    assert _dynamic_imports(t) == [("a", "pkg.mod"), ("b", "other"), ("m", "bench.x")]   # a reassigned spec is forgotten
    assert [line for line, _ in unfollowed_loads(t)] == [5, 9]
    assert literal_paths(ast.parse("P = ROOT / 'scripts' / 'g.py'\nQ = 'a/b.py'\nR = 'b.txt'\n")) == [(1, "scripts/g.py"), (2, "a/b.py")]
