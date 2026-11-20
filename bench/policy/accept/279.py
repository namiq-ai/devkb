"""#279: a renamed, added or deleted code file in the searched scope makes the graph stale for that search, as a modified one does,
so the guardrail never answers a search from a graph that predates the change with lines grep would not print (or without lines it
would). Black box: the checkout's own hook script on a fixture git repository, graph built BEFORE the change, as accept/329."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
MOD = "def handler(a, b):\n    return a + b\n\n\ndef other():\n    return handler(1, 2)\n"
USE = "from pkg.mod import handler\n\nhandler(3, 4)\nhandler(5, 6)\n"
CMD = "grep -rn handler pkg"
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else sys.executable


def git(repo, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=repo, check=True, capture_output=True)


def run_case(td, name, change):
    repo, home = Path(td) / name, Path(td) / (name + "-home")
    (repo / "pkg").mkdir(parents=True)
    (home / ".claude" / "hooks").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("")
    (repo / "pkg" / "mod.py").write_text(MOD)
    (repo / "pkg" / "use.py").write_text(USE)
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "x")
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL="1", DEVKB_TELEMETRY="0",
               PATH=f"{W / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL_TEACH", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, env=env, capture_output=True, timeout=300)
    change(repo)
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": CMD}, "cwd": str(repo), "session_id": name, "tool_use_id": name}
    p = subprocess.run([py, str(W / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), cwd=repo, env=env,
                       capture_output=True, text=True, timeout=120)
    out = p.stdout
    # stale for this search: the search is not replaced by an answer from the older graph (grep runs on the real files)
    return '"deny"' not in out


def rename(repo):
    git(repo, "mv", "pkg/use.py", "pkg/client.py")


def rename_unstaged(repo):
    os.rename(repo / "pkg" / "use.py", repo / "pkg" / "client.py")


def added(repo):
    (repo / "pkg" / "new.py").write_text("from pkg.mod import handler\n\nhandler(7, 8)\n")
    git(repo, "add", "pkg/new.py")


def added_untracked(repo):
    (repo / "pkg" / "new.py").write_text("from pkg.mod import handler\n\nhandler(7, 8)\n")


def deleted(repo):
    git(repo, "rm", "-q", "pkg/use.py")


def deleted_unstaged(repo):
    (repo / "pkg" / "use.py").unlink()


def modified(repo):
    (repo / "pkg" / "use.py").write_text(USE + "handler(9, 9)\n")


with tempfile.TemporaryDirectory() as td:
    for k, f in (("renamed_staged", rename), ("renamed_unstaged", rename_unstaged), ("added_staged", added),
                 ("added_untracked", added_untracked), ("deleted_staged", deleted), ("deleted_unstaged", deleted_unstaged),
                 ("modified_regression_guard", modified)):
        res[k + "_file_never_gets_a_stale_answer"] = run_case(td, k, f)
res["pass"] = all(res.values())
print(json.dumps(res))
