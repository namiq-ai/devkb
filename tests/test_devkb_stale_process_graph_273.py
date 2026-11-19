"""#273: a process graph older than the symbol index makes the graph stale, so no answer uses its old line numbers."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import misses  # noqa: E402


def _git(root, *c):
    subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)


def test_graph_state_reports_the_older_part(tmp_path):
    _git(tmp_path, "init", "-q"); (tmp_path / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", "."); _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "a")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / ".devkb").mkdir()
    (tmp_path / ".devkb" / "symbols-manifest.json").write_text(json.dumps({"git_head": head}))
    (tmp_path / ".devkb" / "manifest.json").write_text(json.dumps({"git_head": "1f14dd5c0571b43edaee4866e1594a778edd37a5"}))
    assert misses.graph_state(tmp_path) == ("1f14dd5c0571b43edaee4866e1594a778edd37a5", head)
    (tmp_path / ".devkb" / "manifest.json").write_text(json.dumps({"git_head": head}))
    assert misses.graph_state(tmp_path) == (head, head)


def test_no_answer_uses_an_older_process_graphs_line_numbers(tmp_path):
    A, home = tmp_path / "a", tmp_path / "home"
    (A / "pkg").mkdir(parents=True); (home / ".claude" / "hooks").mkdir(parents=True)
    (A / "pkg" / "__init__.py").write_text("")
    (A / "pkg" / "core.py").write_text("LIMIT = 3\n\n\ndef compute(x):\n    return x * LIMIT\n")
    (A / "pkg" / "app.py").write_text("from pkg.core import compute\n\n\ndef run():\n    return compute(2)\n")
    _git(A, "init", "-q"); _git(A, "add", "."); _git(A, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "a")
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(PYTHONPATH=str(ROOT), HOME=str(home), DEVKB_MISSLOG="0", PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, check=True)
    (A / "pkg" / "core.py").write_text("\n\n\n\n\nLIMIT = 3\n\n\ndef compute(x):\n    return x * LIMIT\n")
    _git(A, "commit", "-qam", "b")
    subprocess.run([sys.executable, "-P", "-m", "devkb.build_symbols", "--project", str(A)], cwd=A, env=env, capture_output=True)
    out = ""
    for j, c in enumerate(("ls", 'grep -rn "^LIMIT\\|def compute" pkg/')):
        ev = {"session_id": "s273", "tool_use_id": f"t{j}", "tool_name": "Bash", "cwd": str(A), "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev),
                             capture_output=True, text=True, env=env, cwd=A).stdout
    h = json.loads(out).get("hookSpecificOutput", {}) if out.strip().startswith("{") else {}
    text = h.get("permissionDecisionReason", "") + h.get("additionalContext", "")
    assert "pkg/core.py:1:" not in text                     # the old line of LIMIT is never shown
