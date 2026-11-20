"""#331: the `none` arm and a devkb arm run the same test suite. Black box on policybench.checkout of the checkout under
test: build both arms' checkouts from the scoring repository's HEAD (uv, the base-suite run and graph builds stubbed,
nothing else), then count the tests each one collects. Fails on 675 against 986 before the fix."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()                          # the checkout under test (its harness is what is called)
REPO = Path(__file__).resolve().parents[3]               # the repository that runs this check: full tests, source of the arms
sys.path.insert(0, str(W / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = pb.sb
sb.REPO = REPO
sb.CORPUS_REPOS = ()
sb.check_graphs = lambda w: None
for k in list(pb.BASES):
    pb.BASES[k] = "HEAD"
real_run, real_sh = subprocess.run, sb.sh


def run(cmd, *a, **k):
    c = [str(x) for x in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
    if c and (c[0].endswith(".venv/bin/python") or c[0].endswith("/build") or c[0].endswith("devkb")):
        return subprocess.CompletedProcess(cmd, 0, "1 passed in 0.01s\n", "")
    return real_run(cmd, *a, **k)


def sh(cmd, **kw):
    if cmd and cmd[0] == "uv":
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return real_sh(cmd, **kw)


pb.subprocess.run, pb.sb.sh = run, sh


def collected(w: Path) -> int:
    r = real_run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=w, capture_output=True,
                 text=True, env=dict(os.environ, PYTHONPATH=str(w)), timeout=600)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return int(last.split()[0]) if last and last.split()[0].isdigit() else -1


out = {}
with tempfile.TemporaryDirectory() as td:
    counts = {}
    for arm in ("none", "climain"):
        w = Path(td) / arm
        try:
            pb.checkout(w, arm)
        except RuntimeError:                              # a red base is not what is measured here
            pass
        counts[arm] = collected(w)
    out["collected"] = counts
    out["same_suite"] = counts["none"] > 0 and counts["none"] == counts["climain"]
out["pass"] = out["same_suite"]
print(json.dumps(out))
