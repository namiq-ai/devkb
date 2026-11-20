"""A transient failure of `gh issue create` marks the comment as answered: the ticket is never filed and the user never gets a reply."""
import sys, tempfile, json
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "ops" / "triage"))
import triage as t  # noqa: E402

t.HOME = Path(tempfile.mkdtemp())
VERDICT = json.dumps({"action": "ticket", "type": "bug", "priority": "low", "handling": "none", "reply": "thanks",
                      "ticket": {"title": "Crash on empty file", "body": "x" * 120}})
creates, replies, attempts = [], [], []
thread = {"number": 3, "title": "Tell us", "labels": [t.FEEDBACK_LABEL], "pr": False, "number_": 3}
comment = {"id": 55, "url": "u", "author": "someone", "bot": False, "assoc": "NONE", "body": "it crashes", "ours": False}


def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[:3] == ["gh", "issue", "create"]:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("HTTP 502 (transient)")
        creates.append(cmd)
        return "https://github.com/o/r/issues/99"
    if cmd[:3] == ["gh", "issue", "comment"]:
        replies.append(input)
    return ""


t.run, t.claude = fake_run, lambda p, c, tools: (VERDICT, 0.01)
t.comments = lambda n: [comment]
for _ in range(3):                                # three runs: the first hits a transient error
    t.feedback_pass(True, [thread])
print(f"tickets filed: {len(creates)}, replies posted: {len(replies)}; expected 1 and 1 (a later run retries the failed create)")
sys.exit(1 if not creates else 0)
