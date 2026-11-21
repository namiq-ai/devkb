"""refetch(): how often an agent fetches again, by grep or read, what a devkb query just answered."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sb = importlib.import_module("storybench")


def bash(c):
    return ("Bash", {"command": c})


def test_targets_are_names_and_file_base_names():
    t = sb.devkb_targets
    assert t(*bash(".venv/bin/devkb symbol _def_spans --source --project .")) == ["_def_spans"]
    assert t(*bash("devkb outline devkb/cpp_resolve.py --project .")) == ["cpp_resolve.py"]
    assert t(*bash("devkb pack --project . refactor Repo::method_on")) == ["method_on"]      # has an underscore
    assert t(*bash("devkb pack --project . file devkb/packs.py")) == ["packs.py"]
    assert t("mcp__devkb__symbol", {"query": "ReadTools._src"}) == ["_src"]
    assert t(*bash('devkb symbol "re:cpp.*resolve" --project .')) == []        # a regex names no target
    assert t(*bash('devkb docs "how are tests found"')) == []                  # free text neither
    assert t(*bash("devkb symbol ab --project .")) == []                       # under 3 characters
    assert t(*bash("devkb symbol resolve --project .")) == []                  # a word, not a name
    assert t(*bash("devkb symbol cpp --project .")) == [] and t(*bash("devkb symbol constant")) == []
    assert t(*bash("devkb symbol ReadTools")) == ["ReadTools"] and t(*bash("devkb symbol render_uses")) == ["render_uses"]
    assert t(*bash("devkb symbol longidentifier")) == ["longidentifier"]       # nine letters or more
    assert t(*bash("devkb symbol __init__")) == []                             # every class has one


def test_a_grep_or_read_of_the_target_after_the_query_is_a_refetch():
    calls = [bash("devkb symbol mask_source --project ."), ("Read", {"file_path": "/w/devkb/cpp_symbols.py"}),
             bash("grep -n mask_source devkb/*.py")]
    calls = [bash("devkb symbol mask_source --project ."), ("Read", {"file_path": "/w/devkb/cpp_symbols.py"}),
             bash("grep -n mask_source devkb/*.py")]
    assert sb.refetch(calls) == {"queries": 1, "refetched": 1, "grep": 1, "read": 0, "outline_read": 0}   # the Read names no target
    # an outline followed by a read of the file is its use, counted apart; a grep after an outline is a refetch
    assert sb.refetch([bash("devkb outline devkb/cpp_resolve.py"), ("Read", {"file_path": "/w/devkb/cpp_resolve.py", "limit": 50})]) \
        == {"queries": 1, "refetched": 0, "grep": 0, "read": 0, "outline_read": 1}
    assert sb.refetch([bash("devkb outline devkb/cpp_resolve.py"), bash("grep -n scan_body cpp_resolve.py")])["refetched"] == 1


def test_the_same_shell_command_counts_and_a_later_call_outside_the_window_does_not():
    assert sb.refetch([bash("devkb symbol foo_bar --project . ; grep -n foo_bar devkb/x.py")])["refetched"] == 1
    far = [bash("devkb symbol foo_bar --project ."), bash("pytest -q"), bash("git status"), bash("grep -n foo_bar x.py")]
    assert sb.refetch(far)["refetched"] == 0


def test_another_name_or_a_devkb_call_is_not_a_refetch_and_a_name_is_whole_word():
    assert sb.refetch([bash("devkb symbol foo_bar"), bash("grep -n other devkb/x.py")])["refetched"] == 0
    assert sb.refetch([bash("devkb symbol foo_bar"), bash("devkb uses foo_bar")])["refetched"] == 0
    assert sb.refetch([bash("devkb symbol resolve"), bash("grep -n cpp_resolve_all x.py")])["refetched"] == 0


def test_queries_without_a_target_are_not_counted_and_a_run_without_devkb_is_zero():
    assert sb.refetch([bash("devkb docs 'x y'"), bash("grep -n x y")]) == {"queries": 0, "refetched": 0, "grep": 0, "read": 0, "outline_read": 0}
    assert sb.refetch([bash("grep -n a b")])["queries"] == 0


def test_a_transcript_reports_it(tmp_path):
    import json
    ev = [{"type": "assistant", "message": {"id": "m1", "content": [
              {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "devkb symbol mask_source"}}]}},
          {"type": "assistant", "message": {"id": "m2", "content": [
              {"type": "tool_use", "id": "t2", "name": "Grep", "input": {"pattern": "mask_source"}}]}}]
    p = tmp_path / "stream.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in ev))
    assert sb.transcript(p)["refetch"] == {"queries": 1, "refetched": 1, "grep": 1, "read": 0, "outline_read": 0}


def test_the_release_table_shows_refetch_per_run_and_n_a_for_old_rows():
    rt = importlib.import_module("release_table")
    assert rt.refetched([{"rq": 3, "rf": 1}, {"rq": 1, "rf": 1}]) == "1.0/2.0"
    assert rt.refetched([{"rq": None, "rf": None}]) == "n/a" and rt.refetched([]) == "n/a"
    base = {"turns": 5, "calls": {"search": 1}, "ctx_tokens": 10, "cost": 0.1, "seconds": 60, "suite_pass": True, "run": "none-x"}
    assert rt.per_run({**base, "refetch": {"queries": 4, "refetched": 2, "grep": 1, "read": 1}})["rf"] == 2
    assert rt.per_run(base)["rq"] is None
    assert "| Re-fetched |" in Path(rt.__file__).read_text()
