import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({"pkg/__init__.py": "", "pkg/mod.py": "LIMIT = 5\n", "pkg/user.py": "import pkg.mod\n\ndef e():\n    return pkg.mod.LIMIT\n"})
_fx.build(d)
out, _ = _fx.dk(d, "pack", "--project", ".", "change", "LIMIT")
print(out[out.find("## Functions"):])
bad = "pkg/user.py::e" not in out
print("BAD: `pkg.mod.LIMIT` read in e() is not attributed, and the pack still says Complete" if bad else "ok")
print("expected: e() listed as reaching LIMIT (or the pack says Incomplete)")
sys.exit(1 if bad else 0)
