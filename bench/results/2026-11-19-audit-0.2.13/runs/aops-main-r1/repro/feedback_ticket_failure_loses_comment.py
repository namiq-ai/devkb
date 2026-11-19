"""#206: feedback marks a comment as done BEFORE posting. A transient failure of `gh issue create` then means
the comment is never answered and never retried: it is lost with only a log line."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_HOME"] = tempfile.mkdtemp()
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)

thread = {"number": 1, "title": "Tell us what you tried", "body": "", "author": "m", "bot": False, "assoc": "OWNER", "pr": False,
          "labels": ["user-result"], "comments": 1, "updated": "u"}
comment = {"id": 55, "url": "u", "author": "x", "bot": False, "assoc": "NONE", "body": "it crashes on X", "ours": False}
created, replied, fail = [], [], {"on": True}
def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[:3] == ["gh", "issue", "create"]:
        if fail["on"]:
            fail["on"] = False
            raise RuntimeError("gh issue create: HTTP 502")
        created.append(1); return "https://example.test/issues/9"
    if cmd[:3] == ["gh", "issue", "comment"]:
        replied.append(1)
    return ""
t.run = fake_run
t.claude = lambda p, c, tools: ('{"action":"ticket","type":"bug","priority":"low","reply":"thanks","ticket":{"title":"Crash on X","body":"' + "x" * 100 + '"}}', 0.01)
t.comments = lambda n: [comment]
t.update_tree = lambda: None
t.ensure_labels = lambda apply: None
t.items = lambda: [thread]
t.cmd_feedback(True)
t.cmd_feedback(True)       # the next run, GitHub healthy again
print("tickets filed:", len(created), "replies posted:", len(replied))
print("expected: the comment is retried on the next run (1 ticket, 1 reply) once nothing was filed")
sys.exit(1 if not created else 0)
