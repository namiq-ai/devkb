"""#284: the logged question is the graph question the answer came from, and guardrail-stats counts every action the hook logs."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("devkb_guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

Q = [{"name": "helper", "verdict": "complete"}]


def test_a_call_site_answer_is_logged_as_the_uses_question():
    assert g.question_of("substitute", Q, "call-sites", "same-question") == "uses"
    assert g.question_of("alongside", Q, "call-sites-filtered", "cut") == "uses"
    assert g.question_of("alongside", Q, "in-file", "partial-names") == "uses"
    assert g.question_of("alongside", Q, "call-sites", "ambiguous:call-sites") == "uses"
    assert g.question_of("alongside", Q, "unknown", "key") == "uses"


def test_a_definition_or_body_answer_is_symbol_source_and_a_location_list_is_symbol():
    assert g.question_of("read-answer", Q, "read-body", "definition:one") == "symbol --source"
    assert g.question_of("alongside", Q, "read-body", "body:one") == "symbol --source"
    assert g.question_of("substitute", Q, "locate", "same-question") == "symbol"


def test_an_outline_answer_is_the_outline_question_not_none():
    assert g.question_of("alongside", [], "list-symbols", "outline") == "outline"
    assert g.question_of("outline-on-open", [], "", "first-open") == "outline"
    assert g.question_of("span-hint", Q, "", "") == "outline"


def test_a_decision_that_gave_no_answer_logs_what_was_checked():
    assert g.question_of("pass-through", Q, "call-sites", "stale-graph") == f"pack {g.QUESTION}"
    assert g.question_of("pass-through", [], "count", "intent:count") == "none"


def _log(tmp_path, rows):
    p = tmp_path / "devkb-guardrail.log"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_guardrail_stats_counts_outline_on_open_and_any_other_logged_action(tmp_path):
    from devkb import outcomes
    rows = [{"session": "s1", "action": "outline-on-open", "intent": "list-symbols", "repo": "r"},
            {"session": "s1", "action": "outline-on-open", "intent": "list-symbols", "repo": "r"},
            {"session": "s1", "action": "substitute", "intent": "call-sites", "repo": "r"},
            {"session": "s1", "action": "brand-new-action", "intent": "locate", "repo": "r"}]
    out = outcomes.render_guardrail(_log(tmp_path, rows))
    assert "outline-on-open 2" in out and "substitute 1" in out and "brand-new-action 1" in out, out
    assert "| list-symbols | 2" in out or "| list-symbols |" in out
    assert "outline-on-open" in out.split("intent by action:")[1], out
