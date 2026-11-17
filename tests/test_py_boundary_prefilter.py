"""py_boundaries.extract(modules=...) skips files whose records the resolver would drop; the linked result must not change."""
from devkb import boundaries, py_boundaries
from devkb.boundaries import Record


def _repo(tmp_path):
    (tmp_path / "uses_handle.py").write_text("import ctypes\nlib = ctypes.CDLL('x')\n\ndef f():\n    return lib.c_add(1, 2)\n")
    (tmp_path / "uses_ext.py").write_text("import fastmod\n\ndef g():\n    return fastmod.go(3)\n")
    (tmp_path / "noise.py").write_text("import os\n\ndef h():\n    return os.getcwd()\n")
    (tmp_path / "plain.py").write_text("def k():\n    return 1\n")
    return ["uses_handle.py", "uses_ext.py", "noise.py", "plain.py"]


def test_prefilter_does_not_change_what_the_resolver_links(tmp_path):
    files = _repo(tmp_path)
    exports = [Record("export", "c_add", "extern-c", "lib.c", 3, "lib.c::c_add", language="c"),
               Record("export", "fastmod.go", "pyc-api", "ext.c", 9, "ext.c::go", language="c", kind="pyc-method")]
    full = py_boundaries.extract(tmp_path, files)
    fast = py_boundaries.extract(tmp_path, files, modules={"fastmod"})
    assert len(fast) < len(full)                                       # the os.getcwd() record was never built
    key = lambda res: sorted((l.caller, l.callee, l.mechanism) for l in res.links)
    assert key(boundaries.resolve(exports + full)) == key(boundaries.resolve(exports + fast))
    assert key(boundaries.resolve(exports + fast)) == [("uses_ext.py::g", "ext.c::go", "pyc-api"), ("uses_handle.py::f", "lib.c::c_add", "ctypes")]


def test_no_modules_means_every_file_is_read(tmp_path):
    files = _repo(tmp_path)
    assert py_boundaries.extract(tmp_path, files) == py_boundaries.extract(tmp_path, files, modules=None)
