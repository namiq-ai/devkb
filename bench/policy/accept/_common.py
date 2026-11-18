"""Run the checkout's own devkb (python -m devkb.cli, its code, not the release) on its corpus copy."""
import json, subprocess, sys
from pathlib import Path
W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
def devkb(*args, repo):
    p = W / "corpus" / repo
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(p)], cwd=W, capture_output=True, timeout=900)
    return subprocess.run([PY, "-P", "-m", "devkb.cli", *args, "--project", str(p)], cwd=W, capture_output=True,
                          text=True, timeout=300).stdout
def emit(**kw):
    print(json.dumps(kw))
