"""Items whose answer is malformed are retried, and paid for, first on every later run (#205), so ten of them starve every item behind."""
import importlib.util, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", ROOT / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
t.HOME = Path(tempfile.mkdtemp())
t.update_tree = lambda: None
t.ensure_labels = lambda a: None
t.feedback_pass = lambda a, e: None
t.log = lambda *a: None
state = {}                                              # number -> labels
for n in range(1, 12):
    state[n] = []
t.items = lambda: [{"number": n, "title": f"t{n}", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
                    "labels": list(l), "comments": 0, "updated": "u"} for n, l in state.items()]
t.comments = lambda n: []
t.run = lambda cmd, **kw: (state[int(cmd[3])].append(cmd[cmd.index("--add-label") + 1])
                           if cmd[:3] == ["gh", "issue", "edit"] and "--add-label" in cmd else "") or ""
paid = []


def claude(prompt, cwd, tools):
    n = int(re.search(r"#(\d+) \(issue\)", prompt).group(1))
    paid.append(n)
    if n <= 10:
        return "I cannot answer that.", 0.05                 # a model answer that fails validation, every time
    return '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "c"}', 0.05


t.claude = claude
t.cmd_triage(True, None)
first = list(paid)
paid.clear()
t.cmd_triage(True, None)
print("run 1 paid for:", first)
print("run 2 paid for:", paid)
print("item 11 triaged after two runs:", "triaged" in state[11])
print("expected: items that failed are backed off (recorded) so item 11 is triaged by run 2 and the ten are not paid for again first")
sys.exit(1 if "triaged" not in state[11] or paid[:10] == first[:10] and len(paid) == 10 else 0)
