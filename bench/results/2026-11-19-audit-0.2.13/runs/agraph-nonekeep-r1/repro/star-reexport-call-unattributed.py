import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _h

d = _h.make({
 "pkg/__init__.py": "from .core import *\n",
 "pkg/core.py": "def star():\n    return 1\n",
 "use.py": "from pkg import star\ndef a():\n    return star()\n",
 "tests/test_u.py": "import use\ndef test_a():\n    use.a()\n",
})
_h.build(d)
rc, out = _h.dk("pack", "--project", d, "change", "star")
print(out.split("---")[0])
found = "use.py::a" in out
complete = "**Complete.**" in out
print("expected: use.py::a (and tests/test_u.py) listed, or Coverage Incomplete; actual: caller listed =", found, "Complete =", complete)
sys.exit(1 if (not found and complete) else 0)
