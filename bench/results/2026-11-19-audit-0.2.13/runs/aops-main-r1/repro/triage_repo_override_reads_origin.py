"""#208: with TRIAGE_REPO set to another repository, fetches and pushes use REPO_URL but the daemon's own tree
(update_tree), which triage, feedback and plan runs read to judge the report, is still origin/main of the git remote
named `origin` of the checkout the script lives in."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_HOME"] = tempfile.mkdtemp()
os.environ["TRIAGE_REPO"] = "someone-else/other-project"
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
cmds = []
t.run = lambda cmd, *a, **k: cmds.append(cmd) or ""
t.update_tree()
used = [" ".join(c) for c in cmds]
print("REPO_URL:", t.REPO_URL)
print("update_tree commands:", *used, sep="\n  ")
ok = any(t.REPO_URL in c for c in used)
print("expected: the tree the agent reads comes from", t.REPO_URL, "(not from the remote called origin)")
sys.exit(0 if ok else 1)
