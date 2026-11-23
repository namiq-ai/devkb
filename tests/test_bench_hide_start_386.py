"""#386: the location-withheld arms never pass a ticket's "where to start" on silently. A plain `Where to start:` line at a line start is a section, an
inline bold one is withheld, and a body that says it in a form no section catches is refused (the run is recorded as a setup error, never run as a
location-withheld run). A ticket with a normal section gives the prompt it gave before."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")

TAIL = "\n\n**Done when:** the test passes.\n"


def test_a_plain_line_is_a_section():
    _t, body = pb.without_location("t", "**Expected:** ok.\n\nWhere to start: `foo_bar` in `devkb/x.py`." + TAIL)
    assert "foo_bar" not in body and "devkb/x.py" not in body and "(withheld for this benchmark run)" in body and "**Done when:**" in body


def test_an_inline_bold_phrase_is_withheld_not_left_with_its_names_masked():
    _t, body = pb.without_location("t", "**Expected:** ok. **Where to start:** `foo_bar` in `devkb/x.py`." + TAIL)
    assert "foo_bar" not in body and "devkb/x.py" not in body and pb.WITHHELD_LINE in body


def test_an_unrecognised_form_is_refused():
    with pytest.raises(pb.LocationNotWithheld):
        pb.without_location("t", "**Expected:** ok.\n\nWHERE TO START - look at foo_bar in devkb/x.py." + TAIL)
    with pytest.raises(pb.LocationNotWithheld):
        pb.prompt_for("9", "t", "Start where to start: foo_bar, then devkb/x.py.\n", Path("/nonexistent"), hide=True)


def test_a_fenced_mention_and_the_withheld_line_itself_are_not_refused():
    body = "**Reproduce:**\n```\n# where to start reading the log\n```\n\n**Where to start:** `a_func` in `devkb/y.py`." + TAIL
    _t, out = pb.without_location("t", body)
    assert pb.WITHHELD_LINE in out and "a_func" not in out


def test_a_normal_section_gives_the_same_prompt_as_before():
    body = "**Expected:** it works.\n\n**Where to start:** `foo_bar` in `devkb/x.py`." + TAIL
    _t, out = pb.without_location("t", body)
    assert out == "**Expected:** it works.\n\n**Where to start:** (withheld for this benchmark run)\n\n**Done when:** the test passes.\n"


def test_a_run_whose_ticket_cannot_be_withheld_is_recorded_as_a_setup_error_and_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setattr(pb, "template_for", lambda a, issue=None: tmp_path / "t")
    monkeypatch.setattr(pb, "from_template", lambda t, w: (Path(w).mkdir(parents=True), (Path(w) / ".bench-arm.json").write_text("{}")))
    monkeypatch.setattr(pb, "run_prompt", lambda *a, **k: (_ for _ in ()).throw(pb.LocationNotWithheld("no section")))
    msg = pb._run_one("9", "mainhid", 1)
    end = json.loads((tmp_path / "runs" / "p9-mainhid-r1" / "end").read_text())
    assert msg.startswith("error p9-mainhid-r1") and end["exit"] == "error" and "no section" in end["error"]
    assert not (tmp_path / "runs" / "p9-mainhid-r1" / "stream.jsonl").exists(), "the agent was never started"
