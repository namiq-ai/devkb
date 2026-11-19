"""#189: guardrail-stats --project counts only that repository's decisions. #190: a `uses` reply with text matches is
fallback-text, not complete."""
import json
from pathlib import Path

from devkb import outcomes


def test_uses_text_matches_are_fallback_text_not_complete():
    assert outcomes.outcome_of_reply({"name": "x", "mode": "word", "n_hits": 3, "files": []})[0] == "fallback-text"
    assert outcomes.outcome_of_reply({"name": "x", "mode": "word", "n_hits": 0, "files": []})[0] == "no-match"
    assert outcomes.outcome_of_reply({"matches": [{"k": "a.py::f"}], "n": 1})[0] == "complete"


def test_guardrail_stats_for_one_project_leaves_out_other_repositories(tmp_path, capsys):
    log = tmp_path / "g.log"
    rows = [{"session": "s", "repo": str(tmp_path / "a"), "action": "substitute"},
            {"session": "s", "repo": str(tmp_path / "b"), "action": "alongside"}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (tmp_path / "a").mkdir()
    outcomes.main(["--guardrail", "--log", str(log), "--project", str(tmp_path / "a")])
    one = capsys.readouterr().out
    outcomes.main(["--guardrail", "--log", str(log)])
    both = capsys.readouterr().out
    assert one.startswith("1 guardrail decision") and both.startswith("2 guardrail decision")
