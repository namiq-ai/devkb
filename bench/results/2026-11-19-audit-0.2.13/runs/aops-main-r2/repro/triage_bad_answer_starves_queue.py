"""An item whose answer is malformed is retried first in every run; with the per-run limit it starves every item behind it."""
import sys, tempfile, json
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "ops" / "triage"))
import triage as t  # noqa: E402

t.HOME = Path(tempfile.mkdtemp())
t.MAX_TRIAGE = 1
VERDICT = json.dumps({"validity": "valid", "type": "bug", "priority": "low", "handling": "none", "comment": "ok", "summary": "s"})
state = {1: [], 2: []}            # labels per item, as GitHub keeps them
paid = []


def mk(n):
    return {"number": n, "title": f"t{n}", "body": "b", "author": "o", "bot": False, "assoc": "NONE", "pr": False,
            "labels": list(state[n]), "comments": 0, "updated": "t"}


def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[:3] == ["gh", "issue", "edit"] and "--add-label" in cmd:
        state[int(cmd[3])].append(cmd[cmd.index("--add-label") + 1])
    return ""


def fake_claude(prompt, cwd, tools):
    paid.append(1)
    return ("I cannot judge this" if "#1 " in prompt else VERDICT), 0.05    # #1 always gets a malformed answer


t.run, t.claude, t.update_tree, t.ensure_labels = fake_run, fake_claude, lambda: None, lambda apply: None
t.items = lambda: [mk(1), mk(2)]
t.comments = lambda n: []
t.feedback_pass = lambda apply, everything: None
for _ in range(4):
    t.cmd_triage(True, None)
print(f"model calls paid: {len(paid)}; labels of #2 after 4 runs: {state[2]}; expected: #2 triaged once #1 failed")
sys.exit(1 if "triaged" not in state[2] else 0)
