import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({
    "pkg/__init__.py": "from .sub import *\n",
    "pkg/sub.py": "__all__ = ['starfn']\n\ndef starfn():\n    return 3\n",
    "pkg/user.py": "import pkg\nfrom pkg import starfn\n\ndef c():\n    return starfn()\n\ndef g():\n    return pkg.starfn()\n",
    "tests/test_u.py": "from pkg import user\n\ndef test_c():\n    user.c()\n",
})
_fx.build(d)
for kind in ("refactor", "change"):
    out, _ = _fx.dk(d, "pack", "--project", ".", kind, "starfn")
    print(out[out.find("Defined"):out.find("---")])
    resolved = "user.py" in out
    complete = "**Complete" in out
    print(kind, "-> callers found:", resolved, "| says Complete:", complete)
    if complete and not resolved:
        print("BAD: starfn is called from user.py (c, g), reached through `from .sub import *`, yet the pack says Complete with no caller and no test")
        print("expected: the two callers (and tests/test_u.py), or Incomplete naming pkg/user.py")
        sys.exit(1)
print("ok")
