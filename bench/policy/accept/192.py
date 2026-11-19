"""#192 on a finished checkout: a call through a package re-export that the resolver leaves unattributed still counts
against the symbol: `pack change pkg/records.py::run` is not Complete and names app/user.py (the audit's r07 fixture:
`run` is a function and a method Job.run; `from pkg import run; run()` goes through pkg/__init__.py).
Also `import pkg; pkg.run()`."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
BASE = {"pkg/__init__.py": "from .records import run\n",
        "pkg/records.py": "class Job:\n    def run(self):\n        return 0\n\n\ndef run():\n    return 1\n",
        "app/__init__.py": "", "tests/__init__.py": "",
        "tests/test_user.py": "from app.user import caller\n\n\ndef test_caller():\n    assert caller() == 1\n"}


def check(td: Path, name: str, user: str) -> bool:
    root = td / name
    for rel, text in {**BASE, "app/user.py": user}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=W, env=ENV, capture_output=True, timeout=600)
    p = subprocess.run([PY, "-P", "-m", "devkb.cli", "pack", "change", "pkg/records.py::run", "--project", str(root)], cwd=W, env=ENV,
                       capture_output=True, text=True, timeout=300).stdout
    return "**Complete.**" not in p and "app/user.py" in p


with tempfile.TemporaryDirectory() as td:
    out = {"from_import": check(Path(td), "a", "from pkg import run\n\n\ndef caller():\n    return run()\n"),
           "module_attr": check(Path(td), "b", "import pkg\n\n\ndef caller():\n    return pkg.run()\n")}
out["pass"] = all(out.values())
print(json.dumps(out))
