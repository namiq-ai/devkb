"""#295: a failed label edit after the triage comment does not repeat the comment. #296: a failed ticket create is retried, a created one is never filed twice."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)

GOOD = '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "ok"}'


def _item(n, **kw):
    return {"number": n, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": "2026-11-19T00:00:00Z", **kw}


class GH:
    """A stand-in for `gh`: records calls; `fail` names the commands (by their second word) that fail while the list is non-empty."""
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail or {}

    def __call__(self, cmd, *a, **k):
        sub = " ".join(cmd[1:3])
        self.calls.append(sub)
        if self.fail.get(sub):
            self.fail[sub] -= 1
            raise RuntimeError(f"{sub}: HTTP 502")
        return "https://github.com/o/r/issues/99\n" if sub == "issue create" else ""


def _triage_env(monkeypatch, tmp_path, items, answers, gh):
    monkeypatch.setattr(triage, "HOME", tmp_path)
    monkeypatch.setattr(triage, "update_tree", lambda: None)
    monkeypatch.setattr(triage, "ensure_labels", lambda a: None)
    monkeypatch.setattr(triage, "items", lambda: items)
    monkeypatch.setattr(triage, "feedback_pass", lambda a, e: None)
    monkeypatch.setattr(triage, "run", gh)
    monkeypatch.setattr(triage, "claude", lambda *a, **k: (answers.pop(0), 0.01))


def test_a_failed_label_edit_does_not_repeat_the_comment_or_the_model_call(monkeypatch, tmp_path):
    items, gh = [_item(7)], GH(fail={"issue edit": 1})
    _triage_env(monkeypatch, tmp_path, items, [GOOD, GOOD], gh)
    triage.cmd_triage(True, None)                                  # comments, then the first label edit fails
    triage.cmd_triage(True, None)                                  # the item still lacks `triaged`: labels alone are retried
    assert gh.calls.count("issue comment") == 1, gh.calls
    assert gh.calls.count("issue edit") >= 2 and triage.pending_labels() == {}, (gh.calls, triage.pending_labels())


def test_after_the_retry_the_item_is_not_judged_again(monkeypatch, tmp_path):
    items, gh = [_item(7)], GH(fail={"issue edit": 1})
    answers = [GOOD]
    _triage_env(monkeypatch, tmp_path, items, answers, gh)
    triage.cmd_triage(True, None)
    triage.cmd_triage(True, None)
    assert answers == [], "exactly one model call was made"      # a second would have popped from an empty list and raised


# ---- #296 ----
FB = {"action": "ticket", "type": "bug", "priority": "low", "handling": "none", "duplicate_of": None, "reply": "thanks",
      "ticket": {"title": "crash on empty input", "body": "x" * 120}}


def _fb_env(monkeypatch, tmp_path, gh, judged):
    thread = {"number": 3, "title": "feedback", "labels": [triage.FEEDBACK_LABEL], "pr": False}
    comment = {"id": 55, "author": "x", "body": "it crashes", "ours": False, "url": "https://github.com/o/r/issues/3#issuecomment-55"}
    monkeypatch.setattr(triage, "HOME", tmp_path)
    monkeypatch.setattr(triage, "comments", lambda n: [comment])
    monkeypatch.setattr(triage, "new_outside_comments", lambda th, done: [c for c in th if c["id"] not in done])
    monkeypatch.setattr(triage, "run", gh)
    import json
    monkeypatch.setattr(triage, "claude", lambda *a, **k: (judged.append(1) or json.dumps(FB), 0.01))
    return thread


def test_a_failed_ticket_create_is_retried_on_the_next_run(monkeypatch, tmp_path):
    gh, judged = GH(fail={"issue create": 1}), []
    thread = _fb_env(monkeypatch, tmp_path, gh, judged)
    triage.feedback_pass(True, [thread])
    triage.feedback_pass(True, [thread])
    assert gh.calls.count("issue create") == 2 and gh.calls.count("issue comment") == 1, gh.calls
    assert len(judged) == 1, "the retry reuses the verdict instead of paying for a second one"


def test_a_ticket_that_was_created_is_never_filed_twice_when_the_reply_fails(monkeypatch, tmp_path):
    gh, judged = GH(fail={"issue comment": 1}), []
    thread = _fb_env(monkeypatch, tmp_path, gh, judged)
    triage.feedback_pass(True, [thread])
    triage.feedback_pass(True, [thread])
    assert gh.calls.count("issue create") == 1, gh.calls            # created once
    assert gh.calls.count("issue comment") == 2, gh.calls           # the reply is retried
    assert triage.pending() == {}
