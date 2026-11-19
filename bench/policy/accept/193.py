"""#193 on a finished checkout: a dataclass field named like a function never takes that function's calls.

With the checkout's own devkb on three fixtures:
- `same_file`: `run()` in the file that also has a dataclass field `run` resolves to the function;
- `cross_file`: an import of `run` from that module resolves to the function;
- `reexport_pack`: through a package re-export, `pack change run` lists the caller and its test (0.2.12 lost both
  and said Complete).
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")


def repo(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=W, env=ENV, capture_output=True, timeout=600)
    return root


def cli(root, *a):
    return subprocess.run([PY, "-P", "-m", "devkb.cli", *a, "--project", str(root)], cwd=W, env=ENV, capture_output=True, text=True, timeout=300).stdout


REC = "from dataclasses import dataclass\n\n\n@dataclass\nclass Job:\n    run: int = 0\n\n\ndef run():\n    return 1\n"
out = {}
with tempfile.TemporaryDirectory() as td:
    a = repo(Path(td) / "a", {"pkg/__init__.py": "", "pkg/records.py": REC + "\n\ndef caller():\n    return run()\n"})
    # the ticket asks that run() resolve to the function (callers 1, as in v0.2.11), not that a bare `run` pick it: the
    # function is named exactly, and the field must never take the call
    fn, fld = cli(a, "pack", "refactor", "pkg/records.py::run"), cli(a, "pack", "refactor", "pkg/records.py::Job.run")
    out["same_file"] = "return run()" in fn and "return run()" not in fld
    b = repo(Path(td) / "b", {"pkg/__init__.py": "", "pkg/records.py": REC, "app/__init__.py": "",
                              "app/user.py": "from pkg.records import run\n\n\ndef caller():\n    return run()\n"})
    out["cross_file"] = ("app/user.py" in cli(b, "pack", "refactor", "pkg/records.py::run")
                         and "app/user.py" not in cli(b, "pack", "refactor", "pkg/records.py::Job.run"))
    c = repo(Path(td) / "c", {"pkg/__init__.py": "from .records import run\n", "pkg/records.py": REC, "app/__init__.py": "",
                              "app/user.py": "from pkg import run\n\n\ndef caller():\n    return run()\n",
                              "tests/__init__.py": "", "tests/test_user.py": "from app.user import caller\n\n\ndef test_caller():\n    assert caller() == 1\n"})
    p = cli(c, "pack", "change", "run", "--path", "pkg/records.py")
    out["reexport_pack"] = "app/user.py" in p and "tests/test_user.py" in p
    out["reexport_text"] = p[:300]
out["pass"] = out["same_file"] and out["cross_file"] and out["reexport_pack"]
print(json.dumps(out))
