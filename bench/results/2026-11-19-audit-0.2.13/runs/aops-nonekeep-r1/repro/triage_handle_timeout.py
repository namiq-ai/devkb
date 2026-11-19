"""A sandboxed test run that hangs (subprocess.TimeoutExpired) must fail that item (handler-failed), not abort the run."""
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", ROOT / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
tmp = Path(tempfile.mkdtemp())
marks = []
item = {"number": 7, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
        "labels": ["handle:draft-pr"], "comments": 0, "updated": "z"}
item2 = dict(item, number=8, labels=["handle:plan"])
t.HOME = tmp
t.update_tree = lambda: None
t.ensure_labels = lambda a: None
t.items = lambda: [item, item2]
t.mark = lambda n, apply, add, remove=None: marks.append((n, add))
t.post = lambda *a: None
t.log = lambda *a: None


def fake_draft(it, thread, apply):
    # what handle_draft_pr does when the agent wrote a hanging test: sandboxed() -> subprocess.run(timeout=1800)
    raise subprocess.TimeoutExpired(["pytest"], 1800)


t.handle_draft_pr = fake_draft
t.claude = lambda *a: ('{"plan": "p"}', 0.0)
print("TimeoutExpired is a RuntimeError:", issubclass(subprocess.TimeoutExpired, RuntimeError))
try:
    t.cmd_handle(True, None)
    crashed = False
except subprocess.TimeoutExpired:
    crashed = True
print("run aborted by TimeoutExpired:", crashed, "| marks:", marks)
print("expected: #7 marked handler-failed and #8 handled; actual: run aborted, #7 keeps handle:draft-pr and is paid for again next run")
sys.exit(1 if crashed or (7, "handler-failed") not in marks else 0)
