"""#194: build time is linear in typed-receiver calls (0.2.12 rescanned every unresolved call per typed call), and the
typed calls still resolve and still clear their own unresolved records."""
import subprocess
from pathlib import Path

import work_counter

from devkb import build_symbols


def _repo(root: Path, n: int) -> Path:
    files = {"pkg/__init__.py": "", "pkg/core.py": "class Store:\n    def put(self, x):\n        return x\n\n    def get(self, x):\n        return x\n"}
    for i in range(n):
        body = ["from pkg.core import Store", "", ""]
        for j in range(20):
            body += [f"def f{j}(s: Store, obj):", "    s.put(1)", "    s.get(2)", "    obj.get(3)", "    obj.put(4)", "    obj.x.get(5)", ""]
        files[f"pkg/m{i}.py"] = "\n".join(body) + "\n"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i",
                   shell=True, cwd=root, check=True)
    return root


def _work(root: Path) -> int:
    """Lines of build_symbols.py executed by one extract(): the same on every run, unlike seconds (#377)."""
    return work_counter.lines_executed(lambda: build_symbols.extract(root), build_symbols.__file__)[0]


def test_three_times_the_files_take_about_three_times_the_work(tmp_path):
    small, large = _work(_repo(tmp_path / "s", 6)), _work(_repo(tmp_path / "l", 18))
    ratio = large / small
    assert ratio < 3.4, (small, large, ratio)     # a count: linear is 2.99 exactly; with the #194 fix reverted by hand it reads 3.82


def test_typed_calls_still_resolve_to_the_class_method(tmp_path):
    g = build_symbols.extract(_repo(tmp_path / "r", 3))
    callers = {e.src.split("::")[0] for e in g.edges("CALLS") if e.dst == "pkg/core.py::Store.put"}
    assert callers == {"pkg/m0.py", "pkg/m1.py", "pkg/m2.py"}
