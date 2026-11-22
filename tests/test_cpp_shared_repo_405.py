"""#405: the C/C++ index of a build's units is built once, shared by resolve, incomplete_reasons and add_to_graph, and a user that is not resolving a
file sees no per-file state. Counted by constructions, not seconds (#377)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import build_symbols, cpp_resolve  # noqa: E402


def _repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    (r / "a.h").write_text("class A { public: A(int x); int get(); };\n")
    (r / "a.cc").write_text('#include "a.h"\nA::A(int x) {}\nint A::get() { return 1; }\nint use() { A a(1); return a.get(); }\n')
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=r, check=True, capture_output=True)
    return r


def test_one_index_is_built_for_a_whole_build(tmp_path, monkeypatch):
    built = []
    real = cpp_resolve.Repo.__init__
    monkeypatch.setattr(cpp_resolve.Repo, "__init__", lambda self, units: (built.append(1), real(self, units))[1])
    g = build_symbols.extract(_repo(tmp_path))
    assert len(built) == 1, f"{len(built)} indexes built for one build (resolve, incomplete_reasons and add_to_graph share one)"
    assert not cpp_resolve._SHARED, "the build's index is dropped when the build ends"
    assert any(True for _ in g.nodes()) if callable(getattr(g, "nodes", None)) else True


def test_a_shared_index_is_reset_for_each_user():
    units: list = []
    a = cpp_resolve.shared_repo(units)
    a.cur_path = "x/y.cc"
    b = cpp_resolve.shared_repo(units)
    assert a is b and b.cur_path == "", "the same index, with no per-file state left over from resolving"
    other = cpp_resolve.shared_repo([])
    assert other is not b, "another units list gets its own index"
    cpp_resolve.drop_shared_repo()


def test_sees_after_the_directive_index_equals_the_scan_it_replaced():
    """The rule of #290 for `#undef`, over random directive lists: the last `#undef` before the use stands unless a `#define` of the name comes after
    it and before the use. Compared with the linear scan `sees` used to do."""
    import random
    from types import SimpleNamespace as NS
    rnd = random.Random(405)
    for trial in range(300):
        undefs = [("X" if rnd.random() < 0.8 else "Y", rnd.randint(1, 40)) for _ in range(rnd.randint(0, 5))]
        defines = [("X" if rnd.random() < 0.8 else "Y", "b", rnd.randint(1, 40)) for _ in range(rnd.randint(0, 5))]
        masked = NS(undefs=undefs, defines=defines)
        u = NS(rec=NS(masked=masked))
        repo = cpp_resolve.Repo.__new__(cpp_resolve.Repo)
        repo.macros, repo._unit, repo.definers = {"X", "Y"}, {"f.cc": u}, {"X": {"f.cc"}, "Y": {"f.cc"}}
        repo._reach_path, repo._reach = "", set()
        for name in ("X", "Y"):
            for line in range(0, 45):
                undef = max((ln for n, ln in undefs if n == name and ln < line), default=0)
                old = not (undef and not any(n == name and undef < ln < line for n, _b, ln in defines))
                assert repo.sees("f.cc", name, line) == old, (trial, name, line, undefs, defines)
