"""A draft-pr retry after the first attempt pushed its branch (e.g. `gh pr create` failed) is rejected by the push: still never retryable."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "ops" / "triage"))
import triage as t  # noqa: E402

tmp = Path(tempfile.mkdtemp())
for k, v in {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@example.com", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@example.com"}.items():
    os.environ[k] = v


def g(*a, cwd=None):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


bare, seed = tmp / "remote.git", tmp / "seed"
g("init", "-q", "--bare", "-b", "main", str(bare))
g("init", "-q", "-b", "main", str(seed))
(seed / "a.txt").write_text("a\n")
g("add", "-A", cwd=seed); g("commit", "-qm", "init", cwd=seed); g("push", "-q", str(bare), "main", cwd=seed)
t.HOME = tmp / "home"
t.HOME.mkdir()
t.TREE = t.HOME / "devkb"
g("clone", "-q", str(bare), str(t.TREE))
t.REPO_URL = str(bare)                            # the repository gh talks to, here a local one
n = {"claude": 0, "pr": 0}


def fake_run(cmd, cwd=None, input=None, check=True, env=None):
    if cmd[0] == "gh":
        if cmd[1:3] == ["pr", "create"]:
            n["pr"] += 1
            if n["pr"] == 1:
                raise RuntimeError("HTTP 502 on pr create")
            return "https://example.invalid/pr/1"
        return ""
    p = subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True, env=env)
    if check and p.returncode:
        raise RuntimeError(f"{' '.join(cmd[:4])}: {p.stderr.strip()[:300]}")
    return p.stdout


def fake_claude(prompt, cwd, tools):
    n["claude"] += 1
    (Path(cwd) / "fix.txt").write_text(f"fix {n['claude']}\n")
    return '{"summary": "s"}', 0.01


t.run, t.claude = fake_run, fake_claude
t.sandboxed = lambda cmd, work: subprocess.CompletedProcess(cmd, 0, "", "")
it = {"number": 12, "title": "Crash on empty file", "pr": False, "author": "o", "body": "b"}
results = []
for attempt in (1, 2):
    try:
        t.handle_draft_pr(it, [], True)
        results.append("ok")
    except RuntimeError as e:
        results.append(f"failed: {str(e)[:120]}")
    time.sleep(1.2)                               # a retry is a later commit
print("attempt 1 (pr create fails after the push):", results[0])
print("attempt 2 (the maintainer retries):", results[1])
print("expected: the second attempt succeeds")
sys.exit(0 if results[1] == "ok" else 1)
