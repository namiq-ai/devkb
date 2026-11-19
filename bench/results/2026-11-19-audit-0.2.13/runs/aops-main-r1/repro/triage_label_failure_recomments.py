"""#206: the comment is posted first, then labels are added with check=False. If the `triaged` label edit fails
(transient GitHub error), the item stays un-triaged and the next run posts a second comment."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_HOME"] = tempfile.mkdtemp()
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)

labels, posted, fail = [], [], {"on": True}
item = {"number": 7, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
        "labels": labels, "comments": 0, "updated": "u"}
def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[:3] == ["gh", "issue", "comment"]:
        posted.append(input)
    elif cmd[:3] == ["gh", "issue", "edit"]:
        if fail["on"] and "triaged" in cmd:
            fail["on"] = False                  # one transient failure; check=False hides it
            return ""
        if "--add-label" in cmd:
            labels.append(cmd[cmd.index("--add-label") + 1])
    return ""
t.run = fake_run
t.claude = lambda p, c, tools: ('{"validity":"valid","type":"bug","priority":"low","comment":"thanks"}', 0.01)
t.update_tree = lambda: None
t.items = lambda: [item]
t.comments = lambda n: []
t.ensure_labels = lambda apply: None
t.cmd_triage(True, None)
t.cmd_triage(True, None)
print("comments posted on #7 over two runs:", len(posted))
print("expected: 1 (an item that was answered is not answered again)")
sys.exit(1 if len(posted) > 1 else 0)
