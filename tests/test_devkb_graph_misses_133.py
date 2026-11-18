"""#133: a search devkb could not answer, which grep then answered, is logged as a graph miss; `devkb misses` drafts tickets."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE, POST = ROOT / "scripts" / "devkb_guardrail.py", ROOT / "scripts" / "devkb_guardrail_post.py"
FILES = {
    "pkg/__init__.py": "",
    "pkg/alpha.py": "def extract(x):\n    return x\n",
    "pkg/a.py": "class A:\n    def run(self):\n        return 1\n",
    "pkg/b.py": "class B:\n    def run(self):\n        return 2\n",
    "pkg/use.py": "from pkg import alpha\n\n\ndef go(o):\n    o.run()\n    return alpha.extract(1)\n",
    "pkg/lone.py": "class L:\n    def lone_method(self):\n        return 1\n",
    "pkg/lonecall.py": "def go(o):\n    return o.lone_method() + o.lone_method()\n",
    "pkg/note.py": "# phantom_name is only discussed here\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    return root


def run(script, home, event, **extra):
    e = {k: v for k, v in os.environ.items() if k not in ("DEVKB_GUARDRAIL", "DEVKB_MISSLOG")}
    e.update(HOME=str(home), **extra)
    p = subprocess.run([sys.executable, str(script)], input=json.dumps(event), capture_output=True, text=True, env=e,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def search(repo, home, pattern, stdout, n, session="s1", **extra):
    ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": session, "tool_use_id": f"t{n}",
          "tool_input": {"command": f"grep -rn '{pattern}' ."}}
    run(PRE, home, ev, **extra)
    run(POST, home, dict(ev, tool_response={"stdout": stdout, "stderr": ""}), **extra)


def log(repo):
    f = repo / ".devkb" / "graph-misses.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_unresolved_name_found_by_grep_is_logged_once_with_every_field(repo, tmp_path):
    out = "pkg/use.py:10:    return getattr(m, 'nonexistent_zz')()\npkg/use.py:13:def nonexistent_zz():\n"
    before = len(log(repo))
    search(repo, tmp_path, "nonexistent_zz", out, 1)
    new = log(repo)[before:]
    assert len(new) == 1
    r = new[0]
    assert r["kind"] == "graph-missed" and r["verdict"] in ("cannot-resolve", "no-match")
    for k in ("t", "session", "repo", "built_at", "head", "devkb_version", "tool", "pattern", "names", "devkb_query",
              "verdict", "devkb_detail", "grep"):
        assert k in r
    assert r["tool"] == "Bash" and r["names"] == ["nonexistent_zz"] and r["built_at"] == r["head"] != ""
    assert r["grep"]["count"] == 2 and r["grep"]["files"] == ["pkg/use.py"] and r["grep"]["languages"] == ["python"]
    search(repo, tmp_path, "nonexistent_zz", out, 2)                     # same session, verdict and name: not again
    assert len(log(repo)) == before + 1


def test_an_incomplete_answer_is_logged_as_incomplete(repo, tmp_path):
    before = len(log(repo))
    search(repo, tmp_path, "lone_method", "pkg/lonecall.py:2:    return o.lone_method()\n", 3, session="s2")
    new = log(repo)[before:]
    assert [r["kind"] for r in new] == ["graph-incomplete"] and "Incomplete" in new[0]["devkb_detail"]


def test_a_complete_answer_and_comment_only_matches_write_nothing(repo, tmp_path):
    before = len(log(repo))
    search(repo, tmp_path, "extract", "pkg/use.py:6:    return alpha.extract(1)\n", 4, session="s3")
    search(repo, tmp_path, "phantom_name", "pkg/note.py:1:# phantom_name is only discussed here\nREADME.md:3:phantom_name\n",
           5, session="s3")
    assert len(log(repo)) == before


def test_the_switch_turns_the_log_off(repo, tmp_path):
    before = len(log(repo))
    search(repo, tmp_path, "other_missing_name", "pkg/use.py:6:other_missing_name()\n", 6, session="s4", DEVKB_MISSLOG="0")
    assert len(log(repo)) == before


def test_misses_command_groups_and_drafts_tickets_with_reproducible_commands(repo, tmp_path):
    search(repo, tmp_path, "nonexistent_zz", "pkg/use.py:10:x\n", 7, session="s5")
    e = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    out = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "misses", "--project", str(repo)], cwd=repo, env=e,
                         capture_output=True, text=True, timeout=60).stdout
    assert "nonexistent_zz" in out and "**Severity:**" in out and "**Reproduce:**" in out and "**Done when:**" in out
    cmd = next(l for l in out.splitlines() if l.startswith("1. `devkb pack change")).split("`")[1]
    again = subprocess.run(cmd.replace("devkb ", f"{sys.executable} -P -m devkb.cli ", 1), shell=True, cwd=repo, env=e,
                           capture_output=True, text=True).stdout
    assert "cannot resolve" in again


def test_a_cpp_scope_name_is_a_name():
    sys.path.insert(0, str(ROOT))
    from devkb.misses import navigation_names
    assert navigation_names(r"Footer::DecodeFrom\|Footer.DecodeFrom") == ["Footer::DecodeFrom", "Footer.DecodeFrom"]
    assert navigation_names(r"\bfoo\(") == ["foo"] and navigation_names("a.*b") == []


def test_pack_with_no_resolution_returns_text_matches_marked_unresolved(repo):
    sys.path.insert(0, str(ROOT))
    from devkb.packs import Packer
    from devkb.process_api import ProcessAPI
    text = Packer(ProcessAPI(str(repo))).change("phantom_name")
    assert "cannot resolve" in text and "Text matches (not resolved" in text and "pkg/note.py" in text


# ── #131: substitute devkb's answer when the graph has it Complete, otherwise pass through; precise miss record ────────

def pre(repo, home, command, n, session="sub", **extra):
    ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": session, "tool_use_id": f"p{n}",
          "tool_input": {"command": command}}
    out = run(PRE, home, ev, **extra).strip()
    return json.loads(out)["hookSpecificOutput"] if out.startswith("{") else {}


def test_a_complete_answer_is_the_search_result(repo, tmp_path):
    h = pre(repo, tmp_path, "grep -rn 'def extract' .", 1)
    assert h.get("permissionDecision") == "deny"
    assert "Defined at `pkg/alpha.py:1" in h["permissionDecisionReason"] and "Complete" in h["permissionDecisionReason"]
    assert "same search again" not in h["permissionDecisionReason"]


def test_repeating_the_search_runs_grep(repo, tmp_path):
    assert pre(repo, tmp_path, "grep -rn 'def extract' .", 1).get("permissionDecision") == "deny"
    assert pre(repo, tmp_path, "grep -rn 'def extract' .", 2).get("permissionDecision") is None


def test_a_compound_command_keeps_running_with_the_answer_beside_it(repo, tmp_path):
    h = pre(repo, tmp_path, "ls pkg; grep -rn 'def extract' .", 1)
    assert "permissionDecision" not in h and "Defined at `pkg/alpha.py:1" in h.get("additionalContext", "")


def test_an_incomplete_or_unresolved_answer_passes_through(repo, tmp_path):
    for n, cmd in enumerate(["grep -rn 'run(' .", "grep -rn phantom_name ."]):
        assert pre(repo, tmp_path, cmd, n).get("permissionDecision") is None


def test_a_miss_records_each_match_precisely(repo, tmp_path):
    out = "./pkg/lonecall.py:2:    return o.lone_method() + o.lone_method()\n./pkg/lone.py:2:    def lone_method(self):\n"
    search(repo, tmp_path, "lone_method", out, 41, session="precise")
    rows = [r for r in log(repo) if r["session"] == "precise"]
    assert rows, log(repo)
    g = rows[-1]["grep"]
    assert {(m["at"], m["kind"], m["in"]) for m in g["matches"]} == {("pkg/lonecall.py:2", "call", "go"),
                                                                    ("pkg/lone.py:2", "definition", "L")}
    assert g["total"] == 2 and g["hash"].startswith("sha1:") and isinstance(rows[-1]["stale"], bool)
    assert rows[-1]["verdict"] != "stale"


@pytest.mark.parametrize(("flags", "prefix"), [
    ("-rn", ""),
    ("-rnh", ""),
    ("-rnH", "pkg/lonecall.py:"),
])
def test_one_file_search_logs_numbered_code_matches(repo, tmp_path, flags, prefix):
    session = f"one-file-{flags}"
    event = {
        "tool_name": "Bash", "cwd": str(repo), "session_id": session, "tool_use_id": "one-file",
        "tool_input": {"command": f"grep {flags} -e 'lone_method' 'pkg/lonecall.py'"},
    }
    run(PRE, tmp_path, event)
    run(POST, tmp_path, dict(event, tool_response={"stdout": f"{prefix}2:    return o.lone_method()\n"}))
    rows = [r for r in log(repo) if r["session"] == session]
    assert len(rows) == 1
    assert rows[0]["grep"]["matches"] == [{"at": "pkg/lonecall.py:2", "kind": "call", "in": "go"}]


def test_many_files_without_a_filename_do_not_guess(repo, tmp_path):
    session = "many-files-without-name"
    event = {
        "tool_name": "Bash", "cwd": str(repo), "session_id": session, "tool_use_id": "many-files",
        "tool_input": {"command": "grep -rnh 'lone_method' pkg/lone.py pkg/lonecall.py"},
    }
    run(PRE, tmp_path, event)
    run(POST, tmp_path, dict(event, tool_response={"stdout": "2:    return o.lone_method()\n"}))
    assert not any(r["session"] == session for r in log(repo))


def test_the_verdict_is_read_from_the_pack_header_only():
    from devkb import misses
    assert misses.verdict_of("# Graph pack\n\n- `a.py:3: x = 'cannot resolve'`\n\n## Coverage\n**Complete.** ok")[0] == "complete"
    assert misses.verdict_of("# Graph pack: change\n\nThe graph cannot resolve `x`. Search the code.")[0] == "cannot-resolve"


@pytest.mark.parametrize("pattern,names", [("def extract", ["extract"]), ("class Packer", ["Packer"]),
                                           ("Footer::DecodeFrom", ["Footer::DecodeFrom"]), ("could not read", [])])
def test_navigation_names_reads_definition_searches(pattern, names):
    from devkb import misses
    assert misses.navigation_names(pattern) == names
