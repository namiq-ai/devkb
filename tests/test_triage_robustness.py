"""#205-#208: a bad answer or a failed GitHub write fails one item, never the run; retries and dry runs never pay or
fail twice; git and gh always target the same repository."""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)


def _item(n, **kw):
    return {"number": n, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": "2026-11-19T00:00:00Z", **kw}


def _quiet(monkeypatch, tmp_path, items):
    monkeypatch.setattr(triage, "HOME", tmp_path)
    monkeypatch.setattr(triage, "update_tree", lambda: None)
    monkeypatch.setattr(triage, "ensure_labels", lambda a: None)
    monkeypatch.setattr(triage, "items", lambda: items)
    monkeypatch.setattr(triage, "feedback_pass", lambda a, e: None)
    monkeypatch.setattr(triage, "log", lambda k, r: None)


GOOD = '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "c"}'


@pytest.mark.parametrize("bad", ['{"validity": "valid", "type": ["bug"], "priority": "low"}',
                                 '{"validity": "needs_info", "type": "bug", "priority": "low", "questions": 3}',
                                 '{"validity": "valid", "type": {"a": 1}, "priority": "low"}', "not json at all"])
def test_205_a_malformed_triage_answer_fails_its_item_and_the_next_is_triaged(monkeypatch, tmp_path, capsys, bad):
    _quiet(monkeypatch, tmp_path, [_item(1), _item(2)])
    answers = iter([bad, GOOD])
    monkeypatch.setattr(triage, "claude", lambda *a: (next(answers), 0.0))
    assert triage.cmd_triage(False, None) == 0
    out = capsys.readouterr().out
    assert "#1: no verdict" in out and "#2 't': valid bug low" in out


@pytest.mark.parametrize("answer", ['{"text": "x"}', '{"plan": {"a": 1}}', '["plan"]'])
def test_205_a_malformed_plan_marks_handler_failed_and_the_next_item_runs(monkeypatch, tmp_path, answer):
    items = [_item(1, labels=["handle:plan"]), _item(2, labels=["handle:plan"])]
    _quiet(monkeypatch, tmp_path, items)
    monkeypatch.setattr(triage, "wants_handling", lambda it: "plan")
    answers = iter([answer, '{"plan": "do it"}'])
    monkeypatch.setattr(triage, "claude", lambda *a: (next(answers), 0.0))
    marks, posts = [], []
    monkeypatch.setattr(triage, "mark", lambda n, apply, add, remove=None: marks.append((n, add)))
    monkeypatch.setattr(triage, "post", lambda n, body, apply: posts.append(n))
    assert triage.cmd_handle(True, None) == 0
    assert marks == [(1, "handler-failed"), (2, "handled")] and posts == [2]


def test_205_a_feedback_ticket_given_as_a_string_fails_that_comment_only(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, "HOME", tmp_path)
    thread = {"number": 4, "title": "feedback", "labels": [triage.FEEDBACK_LABEL], "pr": False}
    cs = [{"id": i, "url": "u", "author": "a", "bot": False, "assoc": "NONE", "body": "x", "ours": False} for i in (1, 2)]
    monkeypatch.setattr(triage, "comments", lambda n: cs)
    monkeypatch.setattr(triage, "log", lambda k, r: None)
    answers = iter(['{"action": "ticket", "type": "bug", "priority": "low", "ticket": "str"}',
                    '{"action": "reply", "type": "question", "priority": "low", "reply": "ok"}'])
    monkeypatch.setattr(triage, "claude", lambda *a: (next(answers), 0.0))
    posted = []
    monkeypatch.setattr(triage, "post_feedback", lambda t, c, v: posted.append(c["id"]))
    triage.feedback_pass(True, [thread])
    assert posted == [2]


def test_206_a_failed_triage_comment_leaves_the_item_unlabelled_and_the_run_goes_on(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path, [_item(69), _item(70)])
    monkeypatch.setattr(triage, "claude", lambda *a: (GOOD, 0.0))
    calls = []
    def fake_run(cmd, cwd=None, input=None, check=True, env=None):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "comment"] and cmd[3] == "69":
            raise RuntimeError("HTTP 502: Bad Gateway")
        return ""
    monkeypatch.setattr(triage, "run", fake_run)
    assert triage.cmd_triage(True, None) == 0
    edits = [c[3] for c in calls if c[:3] == ["gh", "issue", "edit"]]
    comments = [c[3] for c in calls if c[:3] == ["gh", "issue", "comment"]]
    assert "69" not in edits and "70" in edits and comments == ["69", "70"]


def test_207_a_retry_resets_the_branch_instead_of_failing_on_it(monkeypatch, tmp_path):
    cmds = []
    monkeypatch.setattr(triage, "run", lambda cmd, **kw: cmds.append(cmd) or "")
    monkeypatch.setattr(triage, "worktree_for", lambda name, ref: tmp_path)
    monkeypatch.setattr(triage, "worktree_gitdir", lambda w: (tmp_path / "g", "gitdir: x"))
    monkeypatch.setattr(triage, "claude", lambda *a: (_ for _ in ()).throw(RuntimeError("stop after checkout")))
    with pytest.raises(RuntimeError, match="stop after checkout"):
        triage.handle_draft_pr(_item(42, title="pack crashes on empty file"), [], False)
    co = [c for c in cmds if "checkout" in c][0]
    assert "-B" in co and "-b" not in co and "auto/42-pack-crashes-on-empty-file" in co


def test_207_a_dry_run_judges_an_item_once_until_it_changes(monkeypatch, tmp_path):
    items = [_item(1), _item(2)]
    _quiet(monkeypatch, tmp_path, items)
    calls = []
    monkeypatch.setattr(triage, "claude", lambda *a: (calls.append(1), (GOOD, 0.1))[1])
    for _ in range(3):
        triage.cmd_triage(False, None)
    assert len(calls) == 2
    items[0]["updated"] = "2026-11-20T00:00:00Z"                  # the author changed it: judged again
    triage.cmd_triage(False, None)
    assert len(calls) == 3


def test_208_reviews_and_drafts_fetch_and_push_the_repository_gh_talks_to(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, "REPO", "someone/devkb-fork")
    monkeypatch.setattr(triage, "REPO_URL", "https://github.com/someone/devkb-fork.git")
    cmds = []
    monkeypatch.setattr(triage, "run", lambda cmd, **kw: cmds.append(cmd) or "")
    monkeypatch.setattr(triage, "worktree_for", lambda name, ref: cmds.append(["worktree", ref]) or tmp_path)
    monkeypatch.setattr(triage, "claude", lambda *a: ('{"review": "fine"}', 0.0))
    monkeypatch.setattr(triage, "post", lambda *a: None)
    monkeypatch.setattr(triage, "log", lambda k, r: None)
    triage.handle_review(_item(7, pr=True), [], False)
    fetch = [c for c in cmds if "fetch" in c][0]
    assert "https://github.com/someone/devkb-fork.git" in fetch and "origin" not in fetch
    cmds.clear()
    monkeypatch.setattr(triage, "worktree_gitdir", lambda w: (tmp_path / "g", "gitdir: x"))
    monkeypatch.setattr(triage, "claude", lambda *a: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError):
        triage.handle_draft_pr(_item(8), [], False)
    assert any("fetch" in c and "https://github.com/someone/devkb-fork.git" in c for c in cmds)
    assert ["worktree", "refs/triage/main"] in cmds
    src = Path(triage.__file__).read_text()
    assert '"push", "-q", "origin"' not in src and '"fetch", "-q", "origin", f"pull' not in src
