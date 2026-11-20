"""With TRIAGE_REPO set, update_tree() still fetches git origin's main, so triage, plan and feedback agents read the
wrong repository's code while gh comments on TRIAGE_REPO (#208 fixed reviews and draft pushes only)."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_REPO"] = "someone-else/other-repo"
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
t.TREE = Path(tempfile.mkdtemp()) / "devkb"
t.TREE.mkdir()
cmds = []
t.run = lambda cmd, *a, **k: cmds.append(cmd) or ""
t.update_tree()
print("commands:", *cmds, sep="\n  ")
ok = any(t.REPO_URL in c for c in cmds)
print("expected: the read tree is fetched from", t.REPO_URL, "; actual: from origin only")
sys.exit(0 if ok else 1)
