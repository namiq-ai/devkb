"""#258: a run's turns and output tokens are the session's, not its last message's; devkb self-tests are not devkb use."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
sb = importlib.import_module("storybench")


def _msg(i, out, tools=()):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": {"output_tokens": out},
                                             "content": [{"type": "tool_use", "id": f"t{i}{k}", "name": n, "input": inp}
                                                         for k, (n, inp) in enumerate(tools)]}}


def test_turns_count_every_model_call_and_output_tokens_come_from_the_session_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    lines = [{"type": "system", "subtype": "init", "session_id": "s"}, _msg(1, 10), _msg(1, 12), _msg(2, 20), _msg(3, 30),
             {"type": "result", "num_turns": 1, "usage": {"output_tokens": 30},
              "modelUsage": {"sonnet": {"outputTokens": 400, "inputTokens": 5, "cacheReadInputTokens": 900},
                             "haiku": {"outputTokens": 50}}}]
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    t = sb.transcript(p)
    assert t["turns"] == 3 and t["model_calls"] == 3
    assert t["out_tokens"] == 450                       # every model's session total, not the last message's 30


def test_without_a_result_output_tokens_are_the_largest_value_per_message(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in [_msg(1, 10), _msg(1, 12), _msg(2, 20)]))
    assert sb.transcript(p)["out_tokens"] == 32


def test_a_query_before_the_first_edit_is_navigation_and_after_it_a_self_test(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    nav_venv = ("Bash", {"command": ".venv/bin/devkb outline devkb/cpp_resolve.py --project ."})   # D1 teaches this
    nav = ("Bash", {"command": "devkb symbol compute --project ."})
    fixture = ("Bash", {"command": "devkb pack refactor run --project /tmp/fx"})
    edit = ("Edit", {"file_path": "/w/devkb/cpp_resolve.py", "old_string": "a", "new_string": "b"})
    after = ("Bash", {"command": "cd x && .venv/bin/python -m devkb.cli symbol compute --project ."})
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in [_msg(1, 1, [nav_venv, nav]), _msg(2, 1, [fixture]),
                                                          _msg(3, 1, [("mcp__devkb__symbol", {"name": "x"})]),
                                                          _msg(4, 1, [edit, after])]))
    t = sb.transcript(p)
    assert (t["devkb_nav"], t["devkb_selftest"]) == (3, 2)


def test_an_edit_outside_devkb_code_does_not_make_queries_self_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "guardrail_actions", lambda s: (0, {}))
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in [_msg(1, 1, [("Edit", {"file_path": "/w/docs/notes.md"})]),
                                                          _msg(2, 1, [("Bash", {"command": ".venv/bin/devkb outline devkb/x.py"})])]))
    assert sb.transcript(p)["devkb_nav"] == 1


def test_quoted_and_heredoc_text_is_not_a_devkb_command():
    assert sb.devkb_commands("echo 'devkb symbol x' && cat <<'EOF'\ndevkb uses y\nEOF") == (0, 0)
