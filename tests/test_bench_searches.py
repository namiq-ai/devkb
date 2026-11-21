"""bench/policy/searches.py: one parser for the replay scripts (an audit found each had its own and each missed calls)."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
s = importlib.import_module("searches")


def test_quoted_and_unquoted_patterns_in_any_position_of_a_chain():
    cases = {
        'grep -n "def foo" devkb/x.py': ["def foo"], "grep -rn scan_body devkb/": ["scan_body"], "cd src && rg -n --glob '*.py' 'a\\|b' .": ["a\\|b"],
        "devkb uses X | grep -v test | head": ["test"], "grep -A5 -e 'one' -e two f; grep three g": ["one", "two", "three"],
        "echo 'grep nothing'": [], "pytest -q": [],
        # wrappers, subshells and other command forms an audit found missed
        "git grep -n foo": ["foo"], "xargs grep foo": ["foo"], "timeout 10 grep foo x": ["foo"], "command grep foo x": ["foo"], "(grep foo x)": ["foo"],
        "if grep foo x; then echo; fi": ["foo"], "echo $(grep foo x)": ["foo"], "find . -exec grep -l foo {} +": ["foo"],
        # options and their values
        "grep -rn --exclude-dir node_modules foo .": ["foo"], "rg -j 4 foo": ["foo"], "rg --max-depth 2 foo": ["foo"], "grep --regexp=foo x": ["foo"],
        "grep -T foo x": ["foo"], "grep -e a -e b x": ["a", "b"], "grep -- -foo x": ["-foo"], "grep -rne foo .": ["foo"], "grep -n \\\n foo x": ["foo"],
        "cat <<EOF\ngrep inheredoc\nEOF": [],                                        # a here-document body is text
    }
    for command, want in cases.items():
        assert s.grep_patterns(command) == want, command
    assert s.searches_in("Grep", {"pattern": "foo"}) == ["foo"] and s.searches_in("Read", {"pattern": "x"}) == []


def test_a_call_that_writes_code_is_found_whichever_tool_wrote_it():
    assert s.writes_code("Edit", {"file_path": "/w/devkb/a.py"}) and not s.writes_code("Edit", {"file_path": "/w/notes.bin"})
    assert s.writes_code("Edit", {"file_path": "/w/main.go"}) and s.writes_code("Write", {"file_path": "/w/doc.rst"})
    writes = {
        "sed -i 's/a/b/' devkb/a.py": True, "python3 - <<'E'\nopen('devkb/a.py','w').write('x')\nE": True, "cat > tests/test_x.py <<'EOF'\nx\nEOF": True,
        "git apply fix.patch": True, "echo hi > out.py": True, "tee -a notes.md": True,
        "pytest -q > /dev/null 2>&1": False, "grep -n foo devkb/a.py | head": False, "echo a > /tmp/x.txt": False, "awk '$1 > 3.5' f": False,
        "python -c \"import sys; sys.stdout.write('x')\"": False,
    }
    for command, want in writes.items():
        assert s.writes_code("Bash", {"command": command}) is want, command
    assert not s.writes_code("Read", {"file_path": "/w/devkb/a.py"})


def test_a_run_named_twice_is_replayed_once(tmp_path):
    hr = importlib.import_module("hook_replay")
    d = tmp_path / "p1-ctxhid-r1"
    d.mkdir()
    (d / "stream.jsonl").write_text("")
    assert hr.streams([str(d), str(d / "stream.jsonl"), str(tmp_path)]) == [d / "stream.jsonl"]
