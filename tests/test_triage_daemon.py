"""The triage daemon's decisions that need no GitHub and no model: who is an outsider, what the verdict may say, what is posted."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)


def item(**kw):
    base = {"number": 5, "title": "t", "body": "b", "author": "alice", "bot": False, "assoc": "NONE", "pr": False,
            "labels": [], "comments": 0, "updated": ""}
    return {**base, **kw}


def test_only_outsiders_are_triaged():
    assert triage.needs_triage(item(assoc="NONE"))
    assert triage.needs_triage(item(assoc="FIRST_TIME_CONTRIBUTOR"))
    for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
        assert not triage.needs_triage(item(assoc=assoc))
    assert not triage.needs_triage(item(bot=True))


def test_a_triaged_item_is_not_triaged_again_until_the_author_answers_a_question():
    done = item(labels=["triaged"])
    assert not triage.needs_triage(done)
    waiting = item(labels=["triaged", "needs-info"])
    ours = {"author": "me", "body": triage.MARK, "ours": True}
    assert not triage.needs_triage(waiting, [ours])
    assert not triage.needs_triage(waiting, [ours, {"author": "bob", "body": "x", "ours": False}])
    assert triage.needs_triage(waiting, [ours, {"author": "alice", "body": "here", "ours": False}])


def test_handling_needs_exactly_one_known_handle_label_and_no_outcome_label():
    assert triage.wants_handling(item(labels=["handle:plan"])) == "plan"
    assert triage.wants_handling(item(labels=["handle:plan", "handled"])) is None
    assert triage.wants_handling(item(labels=["handle:draft-pr", "handler-failed"])) is None
    assert triage.wants_handling(item(labels=["handle:plan", "handle:review"])) is None
    assert triage.wants_handling(item(labels=["handle:rm-rf"])) is None
    assert triage.wants_handling(item(labels=["bug"])) is None


GOOD = {"validity": "valid", "type": "bug", "priority": "high", "handling": "draft-pr", "summary": "s", "comment": "c"}


def test_a_verdict_outside_the_vocabulary_is_rejected():
    assert triage.validate(GOOD, {5}, 5)["handling"] == "draft-pr"
    for bad in ({"validity": "close_it"}, {"priority": "urgent!!"}, {"type": "exploit"}):
        with pytest.raises(ValueError):
            triage.validate({**GOOD, **bad}, {5}, 5)


def test_duplicate_must_point_at_another_known_item_and_other_verdicts_carry_none():
    dup = {**GOOD, "validity": "duplicate", "handling": "draft-pr"}
    for bad in (None, 5, 99, "7"):
        with pytest.raises(ValueError):
            triage.validate({**dup, "duplicate_of": bad}, {5, 7}, 5)
    v = triage.validate({**dup, "duplicate_of": 7}, {5, 7}, 5)
    assert v["duplicate_of"] == 7 and v["handling"] == "none"        # a duplicate is not handled
    assert triage.validate({**GOOD, "duplicate_of": 7}, {5, 7}, 5)["duplicate_of"] is None


def test_only_valid_items_are_handled_and_needs_info_must_ask_something():
    assert triage.validate({**GOOD, "validity": "invalid"}, set(), 5)["handling"] == "none"
    with pytest.raises(ValueError):
        triage.validate({**GOOD, "validity": "needs_info", "questions": []}, set(), 5)
    assert triage.validate({**GOOD, "validity": "needs_info", "questions": ["which version?"]}, set(), 5)["handling"] == "none"


def test_labels_come_from_the_fixed_vocabulary():
    v = triage.validate(GOOD, set(), 5)
    add, remove = triage.labels_for(v, is_pr=False)
    assert set(add) == {"triaged", "priority: high", "bug", "handle:draft-pr"} and remove == ["needs-info"]
    for lab in add:
        assert lab in triage.STATE_LABELS or lab in ("bug", "enhancement", "question", "documentation", "duplicate", "invalid")
    pr = triage.validate({**GOOD, "type": "pr", "handling": "review"}, set(), 5)
    assert set(triage.labels_for(pr, is_pr=True)[0]) == {"triaged", "priority: high", "handle:review"}
    ni = triage.validate({**GOOD, "validity": "needs_info", "questions": ["q"]}, set(), 5)
    assert "needs-info" in triage.labels_for(ni, False)[0] and triage.labels_for(ni, False)[1] == []


def test_posted_text_cannot_mention_people_or_hide_html_comments():
    out = triage.sanitize("ping @someone and @org/team <!-- hidden --> ok `@kept`")
    assert "@someone" not in out.replace("`@someone`", "") and "`@org/team`" in out
    assert "hidden" not in out and "`@kept`" in out
    assert len(triage.sanitize("x" * 99999)) <= 3500


def test_the_comment_carries_the_marker_the_questions_and_the_ai_disclosure():
    v = triage.validate({**GOOD, "validity": "needs_info", "questions": ["which version?"], "comment": "Thanks."}, set(), 5)
    text = triage.comment_text(v)
    assert text.startswith(triage.MARK) and "- which version?" in text and "Claude" in text


def test_the_json_object_is_found_in_prose_and_code_fences():
    assert triage.json_object('Sure.\n```json\n{"a": {"b": 1}, "c": "}"}\n```') == {"a": {"b": 1}, "c": "}"}
    with pytest.raises(ValueError):
        triage.json_object("no object here")
