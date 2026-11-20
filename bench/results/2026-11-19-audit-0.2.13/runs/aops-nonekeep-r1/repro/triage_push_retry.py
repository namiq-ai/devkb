"""A draft-pr retry after the branch was pushed but `gh pr create` failed must succeed (#207 fixed only the local branch)."""
import importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", ROOT / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
tmp = Path(tempfile.mkdtemp())
os.environ.update(GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@e.x", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@e.x",
                  GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")


def g(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


bare = tmp / "origin.git"
g("init", "-q", "--bare", "-b", "main", str(bare))
seed = tmp / "seed"
g("init", "-q", "-b", "main", str(seed))
(seed / "a.py").write_text("x = 1\n")
g("add", "-A", cwd=seed)
g("commit", "-qm", "init", cwd=seed)
g("push", "-q", str(bare), "main", cwd=seed)
tree = tmp / "tree"
g("clone", "-q", str(bare), str(tree))
t.HOME = tmp / "home"
t.TREE = tree
t.REPO_URL = str(bare)
attempt = [0]


def claude(prompt, cwd, tools):
    attempt[0] += 1
    (Path(cwd) / "fix.py").write_text(f"v = {attempt[0]}\n")
    return '{"summary": "s"}', 0.0


t.claude = claude
t.sandboxed = lambda cmd, work: subprocess.CompletedProcess(cmd, 0, "", "")
real_run = t.run
fail_pr = [True]


def run(cmd, *a, **k):
    if cmd[0] == "gh":
        if cmd[1:3] == ["pr", "create"] and fail_pr[0]:
            fail_pr[0] = False
            raise RuntimeError("gh pr create: HTTP 502")
        return "https://example.invalid/pr/1"
    return real_run(cmd, *a, **k)


t.run = run
it = {"number": 5, "title": "Crash on x", "body": "b", "author": "u", "pr": False, "labels": [], "comments": 0}
try:
    t.handle_draft_pr(it, [], True)
except RuntimeError as e:
    print("attempt 1 failed after the push, as arranged:", e)
try:
    t.handle_draft_pr(it, [], True)
    print("attempt 2 succeeded")
    ok = True
except RuntimeError as e:
    print("attempt 2 failed:", str(e)[:300])
    ok = False
print("expected: the retry opens the draft PR; actual: the push of the fresh branch is rejected (remote has the first attempt)")
sys.exit(0 if ok else 1)
