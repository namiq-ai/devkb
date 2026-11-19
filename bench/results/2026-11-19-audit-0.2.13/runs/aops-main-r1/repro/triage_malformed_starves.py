"""#205: in apply mode an item whose answer is malformed is judged (and paid for) first on every later run, so
MAX_TRIAGE such items keep every newer item from ever being triaged."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_HOME"] = tempfile.mkdtemp()
os.environ["TRIAGE_MAX_ITEMS"] = "2"
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)

def item(n):
    return {"number": n, "title": f"t{n}", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": "2026-01-01"}
ITEMS = [item(1), item(2), item(3)]            # 1 and 2 always get an unparseable answer; 3 is fine
judged = []
GOOD = '{"validity":"valid","type":"bug","priority":"low","comment":"ok"}'
def fake_claude(prompt, cwd, tools):
    n = int(prompt.split("#")[-1].split(" ")[0]) if False else None
    for i in ITEMS:
        if f"#{i['number']} (issue)" in prompt:
            judged.append(i["number"])
            return ("I cannot decide" if i["number"] in (1, 2) else GOOD), 0.05
t.claude = fake_claude
t.update_tree = lambda: None
t.items = lambda: ITEMS
t.comments = lambda n: []
t.run = lambda *a, **k: ""
t.ensure_labels = lambda apply: None
for _ in range(3):
    t.cmd_triage(True, None)
print("items judged over three apply runs:", judged)
print("expected: item 3 is judged by the second run at the latest (items that failed must not take every slot)")
sys.exit(1 if 3 not in judged else 0)
