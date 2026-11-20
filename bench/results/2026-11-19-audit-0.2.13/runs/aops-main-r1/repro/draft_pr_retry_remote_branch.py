"""#207 fixed the local branch (checkout -B) but not the remote one: when the first attempt pushed auto/N-slug and
`gh pr create` then failed, every retry pushes a new commit to the same branch without --force and is rejected."""
import importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp())
os.environ.update(TRIAGE_HOME=str(tmp / "home"), HOME=str(tmp / "hm"), GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
                  GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@example.com", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@example.com")
(tmp / "hm").mkdir()
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

n = {"claude": 0, "pr": 0}
def fake_claude(prompt, cwd, tools):
    n["claude"] += 1
    (Path(cwd) / "fix.py").write_text(f"y = {n['claude']}\n")
    return '{"summary":"fixed"}', 0.01
real_run = t.run
def fake_run(cmd, *a, **k):
    if cmd[0] == "gh":
        if cmd[:3] == ["gh", "pr", "create"]:
            n["pr"] += 1
            if n["pr"] == 1:
                raise RuntimeError("gh pr create: HTTP 502")      # transient, after the branch was pushed
            return "https://example.test/pull/3"
        return ""
    return real_run(cmd, *a, **k)
t.run, t.claude = fake_run, fake_claude
t.sandboxed = lambda cmd, work: subprocess.CompletedProcess(cmd, 0, "", "")
t.update_tree = lambda: None
t.ensure_labels = lambda apply: None
labels = ["handle:draft-pr"]
item = {"number": 5, "title": "Crash on empty input", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
        "labels": labels, "comments": 0, "updated": "u"}
t.items = lambda: [item]
t.cmd_handle(True, None)                 # attempt 1: pushed, PR creation fails -> handler-failed
print("-- a maintainer removes handler-failed; the next run retries")
t.cmd_handle(True, None)
print("pull requests created:", n["pr"] - 1 if n["pr"] > 1 else 0, "(attempts at gh pr create:", n["pr"], ")")
print("expected: the retry opens the draft PR (the push of the retry is not rejected)")
sys.exit(1 if n["pr"] < 2 else 0)
