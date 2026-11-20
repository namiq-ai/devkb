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

ORIG = "/home/someone/work/p999-main-r1"
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
    assert all(r["action"] in hook_replay.ANSWERS + ("remind", "pass-through", "repeat", "span-hint") for r in rows)
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
