"""#182: a graph that has not seen the working tree's code never replaces a search: a new caller or a second definition
added after the build would be missing from its answer."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"


def build(root):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)


def fresh(tmp_path):
    root = tmp_path / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("def compute(x):\n    return x * 2\n")
    (root / "pkg" / "app.py").write_text("from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    build(root)
    return root


_n = [0]


def denied(root, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env["HOME"] = str(home)
    out = ""
    for j, c in enumerate(("ls", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(root), "session_id": f"s182-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    return h.get("permissionDecision") == "deny"


def test_a_fresh_graph_still_replaces(tmp_path):
    root = fresh(tmp_path)
    assert denied(root, tmp_path, "grep -rn compute .") and denied(root, tmp_path, "grep -rn 'def compute' .")


def test_an_untracked_file_with_a_new_caller_and_definition_stops_replacement(tmp_path):
    root = fresh(tmp_path)
    (root / "pkg" / "late.py").write_text("from pkg.core import compute\n\n\ndef go():\n    return compute(9)\n\n\ndef compute(z):\n    return z\n")
    assert not denied(root, tmp_path, "grep -rn compute .")
    assert not denied(root, tmp_path, "grep -rn 'def compute' .")


def test_a_commit_after_the_build_stops_replacement(tmp_path):
    root = fresh(tmp_path)
    (root / "pkg" / "late.py").write_text("from pkg.core import compute\n\n\ndef go():\n    return compute(9)\n")
    subprocess.run("git add -A && git -c user.name=t -c user.email=t@example.com commit -qm late", shell=True, cwd=root, check=True)
    assert not denied(root, tmp_path, "grep -rn compute .")


def test_a_change_outside_the_searched_folder_does_not_stop_it(tmp_path):
    root = fresh(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.py").write_text("y = 1\n")
    assert denied(root, tmp_path, "grep -rn compute pkg/")
