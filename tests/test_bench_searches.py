"""bench/policy/searches.py: one parser for the replay scripts (an audit found each had its own and each missed calls)."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
s = importlib.import_module("searches")


def test_quoted_and_unquoted_patterns_in_any_position_of_a_chain():
    assert s.grep_patterns('grep -n "def foo" devkb/x.py') == ["def foo"]
    assert s.grep_patterns("grep -rn scan_body devkb/") == ["scan_body"]                       # unquoted
    assert s.grep_patterns("cd src && rg -n --glob '*.py' 'a\\|b' .") == ["a\\|b"]               # after cd, a flag with a value
    assert s.grep_patterns("devkb uses X | grep -v test | head") == ["test"]                 # a filter on another command's output
    assert s.grep_patterns("grep -A5 -e 'one' -e two f; grep three g") == ["one", "three"]
    assert s.grep_patterns("echo 'grep nothing'") == [] and s.grep_patterns("pytest -q") == []
    assert s.searches_in("Grep", {"pattern": "foo"}) == ["foo"] and s.searches_in("Read", {"pattern": "x"}) == []


def test_a_call_that_writes_code_is_found_whichever_tool_wrote_it():
    assert s.writes_code("Edit", {"file_path": "/w/devkb/a.py"}) and not s.writes_code("Edit", {"file_path": "/w/notes.bin"})
    assert s.writes_code("Bash", {"command": "sed -i 's/a/b/' devkb/a.py"})
    assert s.writes_code("Bash", {"command": "python3 - <<'E'\nopen('devkb/a.py','w').write('x')\nE"})
    assert s.writes_code("Bash", {"command": "cat > tests/test_x.py <<'EOF'\nx\nEOF"})
    assert s.writes_code("Bash", {"command": "git apply fix.patch"})
    assert not s.writes_code("Bash", {"command": "pytest -q > /dev/null 2>&1"})
    assert not s.writes_code("Bash", {"command": "grep -n foo devkb/a.py | head"})
    assert not s.writes_code("Read", {"file_path": "/w/devkb/a.py"})


def test_a_run_named_twice_is_replayed_once(tmp_path):
    hr = importlib.import_module("hook_replay")
    d = tmp_path / "p1-ctxhid-r1"
    d.mkdir()
    (d / "stream.jsonl").write_text("")
    assert hr.streams([str(d), str(d / "stream.jsonl"), str(tmp_path)]) == [d / "stream.jsonl"]
