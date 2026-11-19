"""#204 on a finished checkout: `pack refactor` on a name the graph cannot resolve gives the text matches (grouped, marked
not resolved), as `pack change` does, instead of only 'Search the code.'."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    (r / "a.py").write_text("handler = make()\n\n\ndef go():\n    return handler.dispatch_event(1)\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=ENV, capture_output=True, timeout=300)
    out = subprocess.run([PY, "-P", "-m", "devkb.cli", "pack", "refactor", "dispatch_event", "--project", str(r)], cwd=W, env=ENV,
                         capture_output=True, text=True, timeout=120).stdout
res = {"text_matches": "cannot resolve" in out and "Text matches (not resolved" in out and "a.py" in out}
res["pass"] = res["text_matches"]
print(json.dumps(res))
