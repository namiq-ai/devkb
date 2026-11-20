"""triage posts its comment first and swallows a failed label edit: the item stays untriaged and is judged and commented again."""
import sys, tempfile, json
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "ops" / "triage"))
import triage as t  # noqa: E402

t.HOME = Path(tempfile.mkdtemp())
posted, model_calls = [], []
item = {"number": 7, "title": "x", "body": "b", "author": "o", "bot": False, "assoc": "NONE", "pr": False, "labels": [],
        "comments": 0, "updated": "t"}
VERDICT = json.dumps({"validity": "valid", "type": "bug", "priority": "low", "handling": "none", "comment": "ok", "summary": "s"})


def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[:3] == ["gh", "issue", "comment"]:
        posted.append(input)
    elif cmd[:3] == ["gh", "issue", "edit"]:
        if check:
            raise RuntimeError("HTTP 502")
        return ""                                 # check=False: the transient error is swallowed, the label is not set
    return ""


def fake_claude(prompt, cwd, tools):
    model_calls.append(1)
    return VERDICT, 0.01


t.run, t.claude, t.update_tree, t.ensure_labels = fake_run, fake_claude, lambda: None, lambda apply: None
t.items = lambda: [dict(item, labels=list(item["labels"]))]
t.comments = lambda n: []
t.feedback_pass = lambda apply, everything: None
for _ in range(2):                                # two runs; the label edit fails (HTTP 502) in both
    t.cmd_triage(True, None)
print(f"comments posted on #7: {len(posted)}, model calls: {len(model_calls)}; expected 1 and 1 (a failed label must not repeat the comment)")
sys.exit(1 if len(posted) > 1 else 0)
