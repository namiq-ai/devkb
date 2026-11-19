"""#194: build time is linear in typed-receiver calls (0.2.12 rescanned every unresolved call per typed call), and the
typed calls still resolve and still clear their own unresolved records."""
import subprocess
import time
from pathlib import Path

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


def _secs(root: Path) -> float:
    t = time.perf_counter()
    build_symbols.extract(root)
    return time.perf_counter() - t


def test_three_times_the_files_take_about_three_times_as_long(tmp_path):
    small, large = _repo(tmp_path / "s", 60), _repo(tmp_path / "l", 180)
    _secs(small)                                  # warm imports and caches
    # best of three for each size, so a busy machine (the benchmark runs agents in parallel) does not flake it
    ratio = min(_secs(large) for _ in range(3)) / min(_secs(small) for _ in range(3))
    assert ratio < 6, ratio                       # linear is about 3; the 0.2.12 quadratic gave 8 to 9


def test_typed_calls_still_resolve_to_the_class_method(tmp_path):
    g = build_symbols.extract(_repo(tmp_path / "r", 3))
    callers = {e.src.split("::")[0] for e in g.edges("CALLS") if e.dst == "pkg/core.py::Store.put"}
    assert callers == {"pkg/m0.py", "pkg/m1.py", "pkg/m2.py"}
