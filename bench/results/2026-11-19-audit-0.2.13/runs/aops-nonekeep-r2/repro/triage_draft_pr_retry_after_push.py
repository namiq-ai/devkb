"""A draft-pr attempt that pushed its branch but failed at `gh pr create` can never be retried: the retry's new commit
is pushed without force to the same auto/N-slug branch and the remote rejects it (non-fast-forward), so the issue
stays `handler-failed` (#207 fixed only the local `checkout -b`)."""
import importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
for k, v in dict(GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@example.com", GIT_COMMITTER_NAME="a",
                 GIT_COMMITTER_EMAIL="a@example.com", GIT_CONFIG_GLOBAL="/dev/null").items():
    os.environ[k] = v
tmp = Path(tempfile.mkdtemp())


def git(*a, cwd=None):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


remote, seed = tmp / "remote.git", tmp / "seed"
git("init", "-q", "--bare", "-b", "main", str(remote))
git("clone", "-q", str(remote), str(seed))
(seed / "devkb").mkdir()
(seed / "devkb" / "a.py").write_text("x = 1\n")
git("add", "-A", cwd=seed); git("commit", "-qm", "seed", cwd=seed); git("push", "-q", "origin", "HEAD:main", cwd=seed)
t.HOME = tmp / "home"
t.HOME.mkdir()
t.TREE = t.HOME / "devkb"
git("clone", "-q", str(remote), str(t.TREE))
t.REPO_URL = str(remote)
attempt = [0]
real_run = t.run


def run(cmd, *a, **k):
    if cmd[0] == "gh":
        if cmd[1:3] == ["pr", "create"] and attempt[0] == 1:
            raise RuntimeError("HTTP 502: Bad Gateway")      # the push already happened
        return "https://example.invalid/pr/1\n"
    return real_run(cmd, *a, **k)


def claude(prompt, cwd, mode):
    (Path(cwd) / "devkb" / "b.py").write_text(f"y = {attempt[0]}\n")      # the agent's fix differs per attempt
    return '{"summary": "s"}', 0.0


class Done:
    returncode = 0
    stdout = ""
    stderr = ""


t.run, t.claude, t.sandboxed = run, claude, lambda cmd, work: Done()
it = {"number": 9, "title": "Crash on empty input", "body": "b", "author": "x", "bot": False, "assoc": "NONE", "pr": False,
      "labels": ["handle:draft-pr"], "comments": 0, "updated": ""}
results = []
for attempt[0] in (1, 2):
    try:
        t.handle_draft_pr(it, [], True)
        results.append("ok")
    except RuntimeError as e:
        results.append(str(e)[:160])
        print(f"attempt {attempt[0]} failed: {str(e)[:200]}")
print("attempt results:", results)
print("expected: the second attempt (a retry after the maintainers cleared handler-failed) succeeds")
sys.exit(1 if results[1] != "ok" else 0)
