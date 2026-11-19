"""A test that hangs in the sandbox raises subprocess.TimeoutExpired from sandboxed(); cmd_handle catches only
RuntimeError/ValueError/..., so the whole `handle` run aborts, the item is not marked handler-failed and is the
first one retried (and paid for) by every later run (the class of defect #205 fixed for malformed answers).
The 1800 s timeout is cut to 1 s here; the sandbox is a fake `bwrap` that sleeps."""
import importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp())
os.environ.update(TRIAGE_HOME=str(tmp / "home"), HOME=str(tmp / "hm"), GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
                  GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@example.com", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@example.com")
(tmp / "hm").mkdir(); (tmp / "bin").mkdir()
(tmp / "bin" / "bwrap").write_text("#!/bin/sh\nsleep 30\n"); (tmp / "bin" / "bwrap").chmod(0o755)
os.environ["PATH"] = f"{tmp / 'bin'}:{os.environ['PATH']}"
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
g = lambda *a, cwd=None: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout
g("init", "-q", "--bare", "-b", "main", str(tmp / "remote.git"))
g("clone", "-q", str(tmp / "remote.git"), str(tmp / "seed"))
(tmp / "seed" / "a.py").write_text("x = 1\n")
g("add", ".", cwd=tmp / "seed"); g("commit", "-qm", "init", cwd=tmp / "seed"); g("push", "-q", "origin", "HEAD:main", cwd=tmp / "seed")
g("clone", "-q", str(tmp / "remote.git"), str(tmp / "home" / "devkb"))
t.TREE = tmp / "home" / "devkb"; t.HOME = tmp / "home"; t.REPO_URL = str(tmp / "remote.git")

def fake_claude(prompt, cwd, tools):
    (Path(cwd) / "fix.py").write_text("y = 1\n")
    return '{"summary":"fixed"}', 0.01
real_run, real_sub = t.run, subprocess.run
t.run = lambda cmd, *a, **k: "" if cmd[0] == "gh" else real_run(cmd, *a, **k)
t.claude = fake_claude
t.update_tree = lambda: None
t.ensure_labels = lambda apply: None
def short(*a, **k):
    if k.get("timeout") == 1800:
        k["timeout"] = 1
    return real_sub(*a, **k)
subprocess.run = short
labels = ["handle:draft-pr"]
item = {"number": 5, "title": "Crash on empty input", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
        "labels": labels, "comments": 0, "updated": "u"}
t.items = lambda: [item]
marked = []
t.mark = lambda n, apply, add, remove=None: marked.append(add)
try:
    t.cmd_handle(True, None)
    print("run finished; item marked:", marked)
except BaseException as e:  # noqa: BLE001
    print("the handle run aborted with", type(e).__name__, "; item marked:", marked)
    print("expected: the item is marked handler-failed and the run goes on to the next item")
    sys.exit(1)
sys.exit(0 if "handler-failed" in marked else 1)
