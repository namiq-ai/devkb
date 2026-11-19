import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({
    "pkg/__init__.py": "from .sub import *\n",
    "pkg/sub.py": "__all__ = ['subfn']\ndef subfn():\n    return 1\n",
    "app.py": "import pkg\nfrom pkg import subfn\ndef direct():\n    return subfn()\ndef via_pkg():\n    return pkg.subfn()\n",
    "tests/test_app.py": "import app\ndef test_direct():\n    app.direct()\ndef test_via():\n    app.via_pkg()\n",
})
rc, out = devkb(d, "pack", "change", "pkg/sub.py::subfn")
print(out)
missing = [n for n in ("app.py::direct", "app.py::via_pkg") if n not in out]
if missing and "**Complete.**" in out:
    print("DEFECT: callers reached through a star re-export are missing, and the pack still says Complete:", missing)
    print("EXPECTED: both callers and tests/test_app.py listed, or Incomplete")
    sys.exit(1)
print("ok")
