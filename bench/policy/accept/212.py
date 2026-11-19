"""#212 on a finished checkout: `devkb symbol|uses|outline` on a repository with no graph print one line on stderr that
says to build first, exit non-zero, and print no traceback."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
out = {}
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    (r / "a.py").write_text("def f():\n    return 1\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    for cmd in (["symbol", "f"], ["uses", "f"], ["outline", "a.py"]):
        p = subprocess.run([PY, "-P", "-m", "devkb.cli", *cmd, "--project", str(r)], cwd=r, env=ENV, capture_output=True, text=True, timeout=120)
        lines = [l for l in p.stderr.splitlines() if l.strip()]
        out[cmd[0]] = p.returncode != 0 and "Traceback" not in p.stderr and len(lines) == 1 and "build" in lines[0]
out["pass"] = all(out.values())
print(json.dumps(out))
