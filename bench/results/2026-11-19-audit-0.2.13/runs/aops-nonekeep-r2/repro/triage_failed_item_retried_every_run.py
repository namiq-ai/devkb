"""An item whose answer is always malformed is judged (and paid for) again on every apply run, and ten of them starve
the items behind them (limit TRIAGE_MAX_ITEMS=10)."""
import contextlib, importlib.util, io, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
t.HOME = Path(tempfile.mkdtemp())


def item(n):
    return {"number": n, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": "2026-11-19T00:00:00Z"}


# newest first, as GitHub lists them: ten items whose answer never parses, then one good older item
items = [item(n) for n in range(20, 10, -1)] + [item(5)]
t.update_tree = lambda: None
t.ensure_labels = lambda a: None
t.items = lambda: items
t.feedback_pass = lambda a, e: None
t.log = lambda k, r: None
t.run = lambda *a, **k: ""
calls = []


def claude(prompt, cwd, tools):
    calls.append(prompt)
    good = '{"validity":"valid","type":"bug","priority":"low","summary":"s","comment":"c"}'
    return (good if "#5 (" in prompt else "garbage, not json"), 0.01


t.claude = claude
for i in range(3):
    with contextlib.redirect_stdout(io.StringIO()):
        t.cmd_triage(True, None)
judged5 = sum("#5 (" in c for c in calls)
print("model calls over 3 apply runs:", len(calls), "; calls that judged item #5:", judged5)
print("expected: a failing item is not paid for again every run, and item #5 gets judged")
sys.exit(1 if judged5 == 0 else 0)
