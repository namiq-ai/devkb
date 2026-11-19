"""#196 with #197 on a finished checkout: a pack for a module constant lists the functions that read it and their
tests, and says Incomplete naming the file when a star import reads it; `pack refactor` lists the reading files."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
FILES = {"pkg/__init__.py": "", "pkg/settings.py": "RETRIES = 3\n",
         "pkg/use_from.py": "from pkg.settings import RETRIES\n\n\ndef f():\n    return RETRIES + 1\n",
         "pkg/use_star.py": "from pkg.settings import *\n\n\ndef h():\n    return RETRIES * 2\n",
         "tests/__init__.py": "", "tests/test_f.py": "from pkg.use_from import f\n\n\ndef test_f():\n    assert f()\n"}
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    for rel, t in FILES.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(t)
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=ENV, capture_output=True, timeout=600)
    pack = lambda *a: subprocess.run([PY, "-P", "-m", "devkb.cli", "pack", *a, "--project", str(r)], cwd=W, env=ENV,
                                     capture_output=True, text=True, timeout=300).stdout
    c, f = pack("change", "RETRIES"), pack("refactor", "RETRIES")
    out = {"change_readers": "pkg/use_from.py::f" in c, "change_tests": "tests/test_f.py" in c,
           # the ticket: the star-import read "is attributed, or the pack says Incomplete and names that file"
           "change_star_incomplete": "pkg/use_star.py" in c and ("pkg/use_star.py::h" in c or "**Complete.**" not in c),
           "refactor_readers": "pkg/use_from.py" in f and "**Complete.**" not in f}
out["pass"] = all(out.values())
print(json.dumps(out))
