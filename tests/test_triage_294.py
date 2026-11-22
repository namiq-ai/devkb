"""#294: an item whose model answer is malformed is backed off, not judged (and paid for) again on every run, and the items behind it are judged."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)

GOOD = '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "c"}'


def _item(n, **kw):
    return {"number": n, "title": "t", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": "2026-11-19T00:00:00Z", **kw}


def _setup(monkeypatch, tmp_path, items, answers, now):
    judged = []
    monkeypatch.setattr(triage, "HOME", tmp_path)
    monkeypatch.setattr(triage, "update_tree", lambda: None)
    monkeypatch.setattr(triage, "ensure_labels", lambda a: None)
    monkeypatch.setattr(triage, "items", lambda: items)
    monkeypatch.setattr(triage, "feedback_pass", lambda a, e: None)
    monkeypatch.setattr(triage, "run", lambda *a, **k: "")
    monkeypatch.setattr(triage, "MAX_TRIAGE", 2)
    monkeypatch.setattr(triage, "now_ts", lambda: now[0])

    def claude(prompt, tree, mode):
        judged.append(prompt)
        return answers.pop(0), 0.01
    monkeypatch.setattr(triage, "claude", claude)
    return judged


def _numbers(monkeypatch):
    seen = []
    real = triage.untrusted

    def spy(it, *a, **k):
        seen.append(it["number"])
        return real(it, *a, **k)
    monkeypatch.setattr(triage, "untrusted", spy)
    return seen


def test_failed_items_do_not_take_every_slot(monkeypatch, tmp_path):
    items = [_item(1), _item(2), _item(3)]
    now = [1_000_000.0]
    _setup(monkeypatch, tmp_path, items, ["garbage"] * 2 + [GOOD] * 6, now)
    seen = _numbers(monkeypatch)
    triage.cmd_triage(True, None)                 # run 1: limit 2 -> items 1 and 2 are tried and fail
    triage.cmd_triage(True, None)                 # run 2, straight after (as the audit's reproduction): 1 and 2 are backed off
    assert seen[:2] == [1, 2] and 3 in seen[2:], seen    # item 3 is judged by the second run at the latest


def test_a_backed_off_item_comes_back_after_its_wait_and_after_an_edit(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, "HOME", tmp_path)
    now = [1_000_000.0]
    monkeypatch.setattr(triage, "now_ts", lambda: now[0])
    triage.note_failure("5", "u1")
    assert triage.backed_off("5", "u1")
    now[0] += 4 * 3600 + 1
    assert not triage.backed_off("5", "u1"), "the first back-off is 4 hours"
    triage.note_failure("5", "u1")                 # a second failure on the same content waits twice as long
    now[0] += 4 * 3600 + 1
    assert triage.backed_off("5", "u1")
    now[0] += 4 * 3600
    assert not triage.backed_off("5", "u1")
    assert not triage.backed_off("5", "u2"), "an edit is a new question"


def test_an_item_that_keeps_failing_waits_for_an_edit(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, "HOME", tmp_path)
    now = [1_000_000.0]
    monkeypatch.setattr(triage, "now_ts", lambda: now[0])
    for _ in range(triage.GIVE_UP_AFTER):
        triage.note_failure("7", "u1")
    now[0] += 365 * 24 * 3600
    assert triage.backed_off("7", "u1") and not triage.backed_off("7", "u2")


def test_a_success_clears_the_record(monkeypatch, tmp_path):
    items = [_item(1)]
    now = [1_000_000.0]
    _setup(monkeypatch, tmp_path, items, ["garbage", GOOD], now)
    triage.cmd_triage(True, None)
    assert "1" in triage.failures()
    now[0] += 5 * 3600
    triage.cmd_triage(True, None)
    assert "1" not in triage.failures()


def test_a_dry_run_records_and_honours_nothing(monkeypatch, tmp_path):
    items = [_item(1)]
    now = [1_000_000.0]
    _setup(monkeypatch, tmp_path, items, ["garbage"], now)
    triage.cmd_triage(False, None)
    assert triage.failures() == {}
