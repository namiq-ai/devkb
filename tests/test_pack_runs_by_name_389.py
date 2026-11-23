"""#389: `pack file` lists a file that runs a module by name (`runpy.run_module("pkg.mod")`, a `-m pkg.mod` command, a local helper that does either)
among the module's dependents, with the line that runs it. A `-m` with no interpreter (`git commit -m msg`) and a dynamic name are not followed."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from devkb import build_symbols  # noqa: E402
import cpp_support as S  # noqa: E402


def runs(src: str):
    return build_symbols._module_runs(ast.parse(src))


def test_a_runpy_call_a_dash_m_command_and_the_two_helper_shapes():
    got = runs("import runpy, subprocess, sys\n"
               "def a():\n    return runpy.run_module('pkg.mod', run_name='__main__')\n"
               "def b():\n    return subprocess.run([sys.executable, '-m', 'pkg.other', '--x'])\n"
               "def _run(module, argv):\n    runpy.run_module(module, alter_sys=True)\n"
               "cmd = lambda mod, *extra: [py, '-P', '-m', mod, *extra]\n"
               "def c():\n    _run('pkg.third', [])\n    return cmd('pkg.fourth', '--y')\n")
    assert {(w, m) for w, m, _ in got} == {("a", "pkg.mod"), ("b", "pkg.other"), ("c", "pkg.third"), ("c", "pkg.fourth")}, got


def test_a_dash_m_that_is_not_python_and_a_dynamic_name_are_not_followed():
    assert runs("import subprocess\nsubprocess.run(['git', 'commit', '-m', 'update'])\n") == []
    assert runs("import runpy\n\n\ndef f(name):\n    runpy.run_module(name)\n    runpy.run_module('pkg.' + name)\n") == []


def test_a_module_level_run_is_kept_for_the_file():
    assert runs("import runpy\nrunpy.run_module('pkg.mod')\n") == [("<module>", "pkg.mod", 2)]


def test_pack_file_lists_the_runners_with_the_line(tmp_path, monkeypatch):
    files = {"pkg/__init__.py": "", "pkg/mod.py": "def main():\n    return 1\n",
             "tools/a.py": "import runpy\n\n\ndef go():\n    return runpy.run_module('pkg.mod')\n",
             "tools/b.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pkg.mod'])\n",
             "tools/c.py": "import subprocess\nsubprocess.run(['git', 'commit', '-m', 'mod'])\n",
             "src/lib/pkg2/thing.py": "def f():\n    return 1\n", "tools/d.py": "import runpy\nrunpy.run_module('pkg2.thing')\n"}
    _api, packer = S.api(tmp_path, files, monkeypatch)
    dep = packer.file("pkg/mod.py").split("## Files that depend on it")[1].split("\n## ")[0]
    assert "`tools/a.py` — runs it by name: `tools/a.py:5:" in dep and "`tools/b.py` — runs it by name: `tools/b.py:2:" in dep, dep
    assert "tools/c.py" not in dep, "`git commit -m mod` runs nothing"
    assert "tools/d.py" in packer.file("src/lib/pkg2/thing.py"), "a dotted name matches a module under a source root"


def test_a_call_of_another_objects_method_with_a_helper_s_name_is_not_a_run_found_by_the_review_of_416():
    got = runs("import runpy\n\n\ndef run(module):\n    runpy.run_module(module)\n\n\ndef f(config):\n    config.run('pkg.mod')\n    run('pkg.real')\n")
    assert [(w, m) for w, m, _ in got] == [("f", "pkg.real")], got
    method = runs("import runpy\n\n\nclass C:\n    def _go(self, module):\n        runpy.run_module(module)\n\n    def f(self):\n        self._go('pkg.mod')\n")
    assert [(w, m) for w, m, _ in method] == [("C.f", "pkg.mod")], method


def test_dash_m_a_package_runs_its_main_module_found_by_the_review_of_416(tmp_path, monkeypatch):
    files = {"pkg/__init__.py": "", "pkg/__main__.py": "def main():\n    return 1\n",
             "tools/a.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pkg'])\n",
             "tools/b.py": "import runpy\nrunpy.run_module('pkg.__main__')\n"}
    _api, packer = S.api(tmp_path, files, monkeypatch)
    dep = packer.file("pkg/__main__.py").split("## Files that depend on it")[1].split("\n## ")[0]
    assert "`tools/a.py` — runs it by name" in dep and "`tools/b.py` — runs it by name" in dep, dep
