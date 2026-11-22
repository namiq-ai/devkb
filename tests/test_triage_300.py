"""#300: a verdict's duplicate_of must be an item number, and posted text keeps no closing keyword in any form GitHub honours."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)

DUP = {"validity": "duplicate", "type": "bug", "priority": "low", "summary": "s", "comment": "c"}


def test_a_boolean_is_not_an_item_number():
    for bad in (True, False, 1.0, "3"):
        with pytest.raises(ValueError):
            triage.validate({**DUP, "duplicate_of": bad}, {1, 2, 3}, 9)
    assert triage.validate({**DUP, "duplicate_of": 2}, {1, 2, 3}, 9)["duplicate_of"] == 2


def test_a_boolean_duplicate_in_feedback_is_refused_too():
    v = {"action": "reply", "type": "question", "priority": "low", "duplicate_of": 2, "reply": "r"}
    assert triage.validate_feedback(v, {1, 2})["duplicate_of"] == 2          # the same verdict with an item number is accepted
    with pytest.raises(ValueError):
        triage.validate_feedback({**v, "duplicate_of": True}, {1, 2})


@pytest.mark.parametrize("text", ["Fixes GH-5 crash on empty input", "Closes #5 crash", "Resolves octo/repo#5 crash",
                                  "fixed: octo/repo#5 crash", "Closes https://github.com/octo/repo/issues/5 crash",
                                  "resolve https://github.com/octo/repo/pull/7 crash"])
def test_every_closing_form_is_neutralised(text):
    out = triage.clean_title(text)
    assert not triage.CLOSING.search(out), out
    assert not triage.CLOSING.search(out.replace("GH-5", "#5")), out


def test_a_plain_use_of_the_word_is_left_alone():
    assert triage.clean_title("Fix the build on Windows") == "Fix the build on Windows"
    assert triage.clean_title("closes the file handle early") == "closes the file handle early"
