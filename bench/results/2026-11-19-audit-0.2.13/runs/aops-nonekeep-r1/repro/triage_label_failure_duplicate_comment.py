"""A transient failure of the label edit after the triage comment was posted must not make the next run comment again (#206),
and the same for `handled` after a handled item."""
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", ROOT / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
t.HOME = Path(tempfile.mkdtemp())
t.update_tree = lambda: None
t.ensure_labels = lambda a: None
t.feedback_pass = lambda a, e: None
t.log = lambda *a: None
labels, comments_posted, claude_calls = [], [], [0]
t.items = lambda: [{"number": 3, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
                    "labels": list(labels), "comments": 0, "updated": "u"}]


def fake_run(cmd, **kw):
    out = ""
    if cmd[:3] == ["gh", "issue", "comment"]:
        comments_posted.append(kw.get("input"))
    elif cmd[:3] == ["gh", "issue", "edit"]:
        return subprocess.CompletedProcess(cmd, 1, "", "HTTP 502")      # GitHub is down for label edits
    return subprocess.CompletedProcess(cmd, 0, out, "")


t.subprocess.run = fake_run


def claude(*a):
    claude_calls[0] += 1
    return '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "looks real"}', 0.01


t.claude = claude
t.cmd_triage(True, None)
t.cmd_triage(True, None)                       # the next timer run
print(f"comments posted on #3 over two runs: {len(comments_posted)}; model calls paid: {claude_calls[0]}; labels now: {labels}")
print("expected: one comment (or the failure is retried without a second comment); actual: the item never got `triaged`, so every run posts again")
sys.exit(1 if len(comments_posted) > 1 else 0)
