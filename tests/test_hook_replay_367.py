"""#367: the hook replay feeds a run's searches through the guardrail, one decision per search, with its reason,
the characters added and the agent's next call; the run's checkout path is rewritten to the replay's checkout."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import hook_replay  # noqa: E402

ORIG = "/srv/agents/work/p999-main-r1"
FILES = {"pkg/core.py": "def compute_total(rows):\n    return sum(rows)\n\n\ndef other_thing():\n    return compute_total([1])\n",
         "pkg/use.py": "from pkg.core import compute_total\n\n\ndef report():\n    return compute_total([2, 3])\n"}


def _repo(root: Path) -> Path:
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore", HOME=str(root.parent))
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


def _stream(path: Path) -> Path:
    def tool(i, name, inp):
        return {"type": "assistant", "message": {"id": f"m{i}", "content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}
    events = [{"type": "system", "subtype": "init", "cwd": ORIG, "session_id": "s-367"},
              tool(1, "Grep", {"pattern": "compute_total", "path": ORIG, "output_mode": "content"}),
              tool(2, "Read", {"file_path": f"{ORIG}/pkg/core.py"}),
              tool(3, "Bash", {"command": f"grep -rn 'compute_total(' {ORIG}/pkg"}),
              tool(4, "Bash", {"command": "ls pkg && python -m pytest -q"}),
              {"type": "result", "subtype": "success"}]
    path.mkdir(parents=True)
    (path / "stream.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def test_one_decision_per_search_with_reason_chars_and_next_call(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = _repo(tmp_path / "repo")
    run = _stream(tmp_path / "runs" / "p999-main-r1")
    assert hook_replay.main(["--repo", str(repo), str(tmp_path / "runs")]) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    rows, summary = lines[:-1], lines[-1]["summary"]
    assert [(r["i"], r["tool"]) for r in rows] == [(0, "Grep"), (2, "Bash")]          # not the Read, not `ls`
    assert all(r["action"] in hook_replay.ANSWERS + ("remind", "pass-through", "repeat") for r in rows)
    assert rows[0]["next"].startswith("Read: ") and rows[1]["next"].startswith("Bash: ls pkg")
    assert all(r["names"] == ["compute_total"] and r["verdicts"] == ["complete"] for r in rows)   # the path was rewritten
    answered = [r for r in rows if r["action"] in hook_replay.ANSWERS]
    assert answered and all(r["chars"] > 0 for r in answered)
    assert summary["decisions"] == 2 and summary["answers"] == len(answered)
    assert summary["answer_rate"] == round(len(answered) / 2, 3) and summary["chars_max"] >= summary["chars_median"] > 0
    assert run.exists()


def test_a_search_outside_any_graph_passes_through_and_is_counted(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "plain"                                  # no graph built: the guardrail lets grep run
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    _stream(tmp_path / "runs" / "p999-main-r1")
    hook_replay.main(["--repo", str(repo), str(tmp_path / "runs" / "p999-main-r1" / "stream.jsonl")])
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])["summary"]
    assert summary["answers"] == 0 and summary["answer_rate"] == 0.0


def _tool(i, name, inp):
    return {"type": "assistant", "message": {"id": f"m{i}", "content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}


def test_only_delivered_text_counts_streams_are_isolated_and_edits_are_marked(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = _repo(tmp_path / "repo")
    for run in ("p1-main-r1", "p2-main-r1"):                  # the same session id in both: state must not carry over
        d = tmp_path / "runs" / run
        d.mkdir(parents=True)
        events = [{"type": "system", "subtype": "init", "cwd": ORIG, "session_id": "same"},
                  _tool(1, "Bash", {"command": f"grep -rn 'compute_total(' {ORIG}/pkg | head"}),   # a bare head (#393)
                  _tool(2, "Edit", {"file_path": f"{ORIG}/pkg/core.py", "old_string": "a", "new_string": "b"}),
                  _tool(3, "Grep", {"pattern": "compute_total", "path": ORIG, "output_mode": "content"}),
                  {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "hook_name": "PreToolUse:Grep",
                   "stdout": json.dumps({"hookSpecificOutput": {"additionalContext": "devkb, from the graph: x"}})}]
        (d / "stream.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    hook_replay.main(["--repo", str(repo), str(tmp_path / "runs")])
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    rows, summary = lines[:-1], lines[-1]["summary"]
    firsts = [r for r in rows if r["i"] == 0]
    assert len(firsts) == 2 and all(r["reminded"] for r in firsts)      # each stream is its own session
    assert all(r["action"] != "remind" for r in firsts)               # the call's decision, not the reminder after it
    for r in rows:                                                    # an answer is only text that reached the agent
        assert r["delivered"] == (r["chars"] > 0)
        assert not (r["delivered"] and r["printed_reminder"])          # the reminder printed after a lost answer is not one
        if r["delivered"]:
            assert r["printed"] and r["action"] in hook_replay.ANSWERS
    assert summary["answers"] == sum(r["delivered"] for r in rows)
    assert [r["after_edit"] for r in rows if r["i"] == 2] == [True, True]
    assert all(r["live_chars"] == len("devkb, from the graph: x") for r in rows if r["i"] == 2)
    assert summary["live_recorded"] == 2


def test_a_cd_is_kept_for_the_next_calls_and_home_paths_are_rewritten():
    home = str(Path.home())
    assert hook_replay.rewrite({"command": "cd ~/w/run && ls"}, f"{home}/w/run", "/x") == {"command": "cd /x && ls"}
    assert hook_replay.CD.match("cd corpus/fmt && grep -n x src").group(1) == "corpus/fmt"
    assert hook_replay.edits({"name": "Bash", "input": {"command": "sed -i 's/a/b/' f.py"}})
    assert hook_replay.edits({"name": "Bash", "input": {"command": "echo x > pkg/new.py"}})
    assert hook_replay.edits({"name": "Bash", "input": {"command": "cd pkg && sed -i 's/a/b/' core.py"}})   # after &&
    for cmd in ("grep -n x f.py 2>&1 | head", "devkb build --project . >/dev/null 2>&1", 'grep -n "x > y" a.py',
                "cat > /tmp/t.py <<'E'\nprint(1)\nE", "git diff > /tmp/d.txt"):
        assert not hook_replay.edits({"name": "Bash", "input": {"command": cmd}}), cmd


def test_live_output_goes_to_the_call_of_its_tool_and_refusals_are_read(tmp_path):
    s = tmp_path / "stream.jsonl"
    ev = [_tool(1, "Read", {"file_path": "a.py"}), _tool(2, "Grep", {"pattern": "x"}),
          {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "hook_name": "PreToolUse:Read", "stdout": ""},
          {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "hook_name": "PreToolUse:Grep",
           "stdout": json.dumps({"hookSpecificOutput": {"permissionDecisionReason": "devkb answered"}})},
          _tool(3, "Bash", {"command": "cd sub && ls"}),
          {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t3", "is_error": True,
                                                      "content": "This command requires approval"}]}}]
    s.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    live, refused = hook_replay.live_outputs(s)
    assert live == {"t1": "", "t2": "devkb answered"} and refused == {"t3"}


def test_a_refused_call_moves_no_directory_edits_nothing_and_live_answers_without_a_decision_count(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = _repo(tmp_path / "repo")
    d = tmp_path / "runs" / "p3-main-r1"
    d.mkdir(parents=True)
    refusal = lambda i: {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True,
                                                                   "content": "This command requires approval"}]}}
    hook = lambda name, text: {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "hook_name": f"PreToolUse:{name}",
                               "stdout": json.dumps({"hookSpecificOutput": {"additionalContext": text}}) if text else ""}
    events = [{"type": "system", "subtype": "init", "cwd": ORIG, "session_id": "s3"},
              _tool(1, "Bash", {"command": "cd pkg && sed -i 's/a/b/' core.py"}), hook("Bash", ""), refusal(1),
              _tool(2, "Grep", {"pattern": "compute_total", "path": ORIG, "output_mode": "content"}), hook("Grep", ""),
              _tool(3, "Bash", {"command": "cd pkg && ls"}), hook("Bash", ""),
              _tool(4, "Grep", {"pattern": "compute_total", "path": ".", "output_mode": "content"}), hook("Grep", ""),
              _tool(5, "Bash", {"command": "ls"}), hook("Bash", "devkb, from the graph: an answer the replay never decided on")]
    (d / "stream.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    hook_replay.main(["--repo", str(repo), str(d)])
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    rows, summary = lines[:-1], lines[-1]["summary"]
    by_i = {r["i"]: r for r in rows}
    assert by_i[1]["cwd"] == "." and not by_i[1]["after_edit"]        # the refused cd and sed -i did nothing
    assert by_i[3]["cwd"] == "pkg"                                      # the cd that ran moved the session
    undecided = [r for r in rows if r.get("undecided")]
    assert [r["i"] for r in undecided] == [4] and summary["live_answers_without_a_decision"] == 1
