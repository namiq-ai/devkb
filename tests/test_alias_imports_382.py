"""#382: a test that binds a module to a short alias (`sb = importlib.import_module("storybench")`, or
`spec_from_file_location` + `module_from_spec`) is among the module's tests to run; a test that names a script by
path is listed as such; a load by a computed name says the list may be incomplete. None of it may add a false caller
or a false test, or drop one the graph found before."""
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

HEAD = "import importlib\nimport importlib.util\nimport os\nimport subprocess\nimport sys\nfrom pathlib import Path\n\n" \
       "HERE = Path(__file__).resolve().parents[1]\n"
INSERT = HEAD + "sys.path.insert(0, str(HERE / \"tools\"))\n"          # 9 lines
FILES = {
    "tools/storyline.py": "def count_turns(rows):\n    return len(rows)\n",
    "tools/runme.py": "def main():\n    print('ok')\n",
    "tools/dynamo.py": "def spin():\n    return 3\n",
    "tools/g.py": "def only_here():\n    return 1\n",
    "other/g.py": "def only_here():\n    return 2\n",
    "alpha/alpha.py": "def run_job(x):\n    return x\n",
    "beta/beta.py": "def run_job(x):\n    return -x\n",
    "vendor/pkg/tool.py": "def frob_it(x):\n    return x\n",
    "bench/cpp/loaded.py": "def measure():\n    return 1\n",
    "bench/exercises/cpp/other.py": "def score():\n    return 1\n",
    "lib/plain.py": "def plain():\n    return 1\n",
    "tests/test_alias.py": INSERT + "sl = importlib.import_module(\"storyline\")\n\n\n"
                                    "def test_count():\n    assert sl.count_turns([1]) == 1\n",
    # the basename is in two directories, and the directory is a module-level name: only tools/g.py is meant
    "tests/test_spec.py": HEAD + "TOOLS = HERE / \"tools\"\n"
                                 "spec = importlib.util.spec_from_file_location(\"gk\", TOOLS / \"g.py\")\n"
                                 "gm = importlib.util.module_from_spec(spec)\n\n\n"
                                 "def test_here():\n    assert gm.only_here() == 1\n",
    "tests/test_run.py": HEAD + "SCRIPT = HERE / \"tools\" / \"runme.py\"\n\n\n"
                                "def test_runs():\n    subprocess.run([sys.executable, str(SCRIPT)], check=True)\n",
    "tests/test_dyn.py": INSERT + "dm = importlib.import_module(os.environ.get(\"DYN\", \"dyn\" + \"amo\"))\n\n\n"
                                  "def test_spin():\n    assert dm.spin() == 3\n",
    # one local name, two modules, in two functions: following either binding would be wrong for the other
    "tests/test_two.py": HEAD + "sys.path.insert(0, str(HERE / \"alpha\"))\nsys.path.insert(0, str(HERE / \"beta\"))\n\n\n"
                                "def test_a():\n    m = importlib.import_module(\"alpha\")\n    assert m.run_job(1) == 1\n\n\n"
                                "def test_b():\n    m = importlib.import_module(\"beta\")\n    assert m.run_job(1) == -1\n",
    # a path that comes from the environment: not followed, so the `.py` literal still resolves it, as before #382
    "tests/test_vendor.py": HEAD + "spec = importlib.util.spec_from_file_location(\"t\", os.path.join(os.environ.get(\"V\", \"/x\"), \"tool.py\"))\n"
                                   "t = importlib.util.module_from_spec(spec)\n\n\n"
                                   "def test_frob():\n    assert t.frob_it(1) == 1\n",
    # bound, but `g` is in two directories so it resolves to neither; the `.py` literal resolved it before #382
    "tests/test_ambig.py": HEAD + "gm = importlib.import_module(\"g\")\nWHERE = \"tools/g.py\"\n\n\n"
                                  "def test_g():\n    assert gm.only_here() == 1\n",
    # a computed load with no directory on sys.path: a plugin; no file is said to be incomplete because of it
    "tests/test_plug.py": "import importlib\nimport os\n\n\ndef test_plugins():\n"
                          "    for n in os.environ.get(\"P\", \"json\").split(\",\"):\n        importlib.import_module(n)\n",
    # loads from bench/cpp only, by a computed file name
    "tests/test_bench_load.py": HEAD + "BENCH = HERE / \"bench\" / \"cpp\"\n\n\n"
                                       "def _load(name):\n"
                                       "    spec = importlib.util.spec_from_file_location(name, BENCH / f\"{name}.py\")\n"
                                       "    m = importlib.util.module_from_spec(spec)\n    return m\n\n\n"
                                       "def test_load():\n    assert _load(\"loaded\")\n",
    # paths that are data or a fixture in tmp_path, not a file of the repository
    "tests/test_data.py": "from pathlib import Path\n\n\ndef test_fixture(tmp_path):\n"
                          "    (tmp_path / \"lib\" / \"plain.py\").write_text(\"x\")\n"
                          "    assert (\"tools/runme.py\", True) and \"lib/plain.py\"\n",
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


def test_aliases_are_followed_and_only_to_the_module_meant(tmp_path):
    p = _packer(tmp_path)
    assert "`tests/test_alias.py`" in _tests(p.file("tools/storyline.py"))
    assert "tests/test_alias.py" in p.change("count_turns")              # the change pack sees the same call
    assert "`tests/test_spec.py`" in _tests(p.file("tools/g.py"))        # through TOOLS, not the bare `g.py`
    assert "test_spec" not in _tests(p.file("other/g.py"))


def test_one_name_for_two_modules_gives_no_false_edge(tmp_path):
    p = _packer(tmp_path)
    alpha, beta = _tests(p.file("alpha/alpha.py")), _tests(p.file("beta/beta.py"))
    assert "test_two.py:20" not in alpha and "test_two.py:15" not in beta  # neither function's call goes to the other


def test_an_unfollowed_or_unresolved_alias_keeps_the_literal_rule(tmp_path):
    p = _packer(tmp_path)
    assert "`tests/test_vendor.py`" in _tests(p.file("vendor/pkg/tool.py"))
    assert "`tests/test_ambig.py`" in _tests(p.file("tools/g.py"))


def test_a_test_that_runs_a_script_by_path_is_listed_and_run(tmp_path):
    p = _packer(tmp_path)
    text = p.file("tools/runme.py")
    assert "`tests/test_run.py` — names it by path: `tests/test_run.py:9:" in _tests(text)
    assert "tests/test_run.py" in text.split("Run: `", 1)[1].split("`", 1)[0]
    assert "test_data" not in text                                      # a string of data names no file
    assert "test_data" not in p.file("lib/plain.py")                    # nor does a fixture written in tmp_path


def test_a_load_by_a_computed_name_says_the_list_may_be_incomplete_where_it_may_load(tmp_path):
    p = _packer(tmp_path)
    assert "may be incomplete" in _tests(p.file("tools/dynamo.py")) and "tests/test_dyn.py:10" in _tests(p.file("tools/dynamo.py"))
    assert "may be incomplete" not in _tests(p.file("lib/plain.py"))    # the plugin load names no directory
    assert "tests/test_bench_load.py" in _tests(p.file("bench/cpp/loaded.py"))
    assert "may be incomplete" not in _tests(p.file("bench/exercises/cpp/other.py"))
    assert "may be incomplete" in p.change("spin").split("## Test files to run", 1)[1]


def test_a_bare_name_counts_by_path_only_when_one_file_has_it(tmp_path):
    p = _packer(tmp_path)
    (tmp_path / "tests" / "test_bare.py").write_text(HEAD + "G = HERE / \"g.py\"\n\n\ndef test_g():\n    assert G\n")
    p._loads = None
    assert "test_bare" not in p.file("tools/g.py") and "test_bare" not in p.file("other/g.py")


def test_the_parsers_follow_only_literals():
    t = ast.parse("import importlib, importlib.util as u, sys\nfrom pathlib import Path\nfrom importlib import import_module\n"
                  "ROOT = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(ROOT / 'bench' / 'policy'))\n"
                  "a = importlib.import_module('pkg.mod')\nb = import_module('other')\nc = importlib.import_module(name)\n"
                  "d = importlib.import_module('.rel', 'pkg')\n"
                  "s = u.spec_from_file_location('x', ROOT / '..' / 'bench' / 'x.py')\nm = u.module_from_spec(s)\n"
                  "s2 = u.spec_from_file_location(name='y', location=ROOT / 'scripts' / 'y.py')\nk = u.module_from_spec(s2)\n"
                  "s3 = u.spec_from_file_location('z', go(tmp, 'climain') / 'z.py')\nn3 = u.module_from_spec(s3)\n")
    got = _dynamic_imports(t)
    assert ("a", "bench.policy.pkg.mod") in got and ("a", "pkg.mod") in got   # where the insert put it, first
    assert got.index(("a", "bench.policy.pkg.mod")) < got.index(("a", "pkg.mod"))
    assert ("m", "bench.x") in got and ("k", "scripts.y") in got
    assert not any(local in ("c", "d", "n3") for local, _ in got)       # computed, relative, a call's argument
    assert [line for line, _ in unfollowed_loads(t)] == [8]                # s3 names no directory
    paths = ast.parse("from pathlib import Path\nR = Path(__file__).parents[1]\nP = R / 'scripts' / 'g.py'\n"
                      "Q = 'a/b.py'\ndef f(tmp_path):\n    return tmp_path / 'x' / 'c.py'\n")
    assert literal_paths(paths) == [(3, "scripts/g.py")]
