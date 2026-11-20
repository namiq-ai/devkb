"""#158: the graph is rebuilt with the right devkb at every merge, rebase and checkout, and a failed rebuild is visible.

Black box on a fixture repository: the checkout's own `devkb init --hooks`, then real version-control operations. A decoy `devkb`
that records its call sits first on PATH, standing in for the released devkb the hooks used to pick up.
- hooks_four: post-commit, post-merge, post-checkout and post-rewrite are all written, each with a devkb block;
- hook_absolute_path: each hook calls an absolute path that exists, and never the bare name `devkb`;
- decoy_never_called: after commit, merge, rebase and checkout the PATH devkb was not run;
- merge_logged / rebase_logged / checkout_logged: each leaves a line naming the new HEAD in .devkb/build.log;
- log_has_exit_and_time: a log line carries an exit code (0 for a good build);
- manifest_head_after_merge: .devkb/manifest.json's git_head equals HEAD after a merge;
- burst_consistent: after a burst of checkouts the graph ends at HEAD and `devkb symbol` answers;
- failed_build_reported: with the graph directory unwritable a commit's rebuild fails, and the next `devkb symbol` says so.
Not tested black-box: that two builds never overlap (no observable beyond timing)."""
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
PY = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else sys.executable
VC = "git"
ID = ["-c", "user.name=t", "-c", "user.email=t@example.com"]


MISSED = [0]


def wait(pred, secs=20):
    """Poll; once something has failed to show up, later waits are short so a failing run stays inside two minutes."""
    end = time.time() + (secs if not MISSED[0] else 4)
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.5)
    ok = pred()
    MISSED[0] += 0 if ok else 1
    return ok



with tempfile.TemporaryDirectory() as td:
    T = Path(td)
    A, home, fake = T / "a", T / "home", T / "fakebin"
    for d in (A, home, fake):
        d.mkdir()
    called = T / "decoy-called"
    (fake / "devkb").write_text(f'#!/bin/sh\necho "$@" >> {called}\nexit 0\n')
    (fake / "devkb").chmod(0o755)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", PATH=f"{fake}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)

    def vc(*a):
        return subprocess.run([VC, *ID, *a], cwd=A, env=env, capture_output=True, text=True, timeout=120, check=True)

    def head():
        return vc("rev-parse", "HEAD").stdout.strip()

    def cli(*a):
        return subprocess.run([PY, "-P", "-m", "devkb.cli", *a], cwd=A, env=env, capture_output=True, text=True, timeout=300)

    def log():
        p = A / ".devkb" / "build.log"
        return p.read_text() if p.exists() else ""

    def logged(h):
        return wait(lambda: h in log() or h[:7] in log())

    def commit(name, body, msg):
        (A / name).write_text(body)
        vc("add", ".")
        vc("commit", "-qm", msg)

    vc("init", "-q", "-b", "main")
    commit("m.py", "def foo():\n    return 1\n", "x")
    cli("init", "--project", str(A), "--hooks")
    vc("add", ".")
    vc("commit", "-qm", "devkb files")
    hdir = A / ".git" / "hooks"
    names = ("post-commit", "post-merge", "post-checkout", "post-rewrite")
    texts = {n: (hdir / n).read_text() if (hdir / n).exists() else "" for n in names}
    res["hooks_four"] = all("devkb" in t for t in texts.values())

    def abs_ok(t):
        if not t or re.search(r"(^|[\s(;&|])devkb(\s|$)", t):
            return False
        return any(Path(m).exists() for m in re.findall(r"/[^\s\"'()&;|]+", t.replace("#!/bin/sh", "")))
    res["hook_absolute_path"] = all(abs_ok(t) for t in texts.values())
    mf = A / ".devkb" / "manifest.json"
    wait(lambda: mf.exists())

    def mhead():
        try:
            return json.loads(mf.read_text()).get("git_head", "")
        except Exception:
            return ""

    # merge
    vc("checkout", "-q", "-b", "feat")
    commit("f.py", "def feat():\n    return 2\n", "feat")
    vc("checkout", "-q", "main")
    commit("g.py", "def other():\n    return 3\n", "other")
    vc("merge", "-q", "--no-ff", "-m", "merge", "feat")
    h = head()
    res["merge_logged"] = logged(h)
    res["manifest_head_after_merge"] = wait(lambda: mhead() == h)

    # rebase
    vc("checkout", "-q", "feat")
    commit("f2.py", "def feat2():\n    return 4\n", "feat2")
    vc("checkout", "-q", "main")
    commit("h.py", "def more():\n    return 5\n", "more")
    vc("checkout", "-q", "feat")
    old = head()
    vc("rebase", "-q", "main")
    h = head()
    res["rebase_logged"] = h != old and logged(h)

    # checkout
    vc("checkout", "-q", "main")
    h = head()
    res["checkout_logged"] = logged(h)
    res["log_has_exit_and_time"] = any(re.search(r"(exit|rc|code)\D{0,6}0\b", ln, re.I) and re.search(r"\d", ln)
                                       for ln in log().splitlines() if h[:7] in ln)

    # a burst of checkouts
    for i in range(4):
        vc("checkout", "-q", "feat" if i % 2 == 0 else "main")
    h = head()
    res["burst_consistent"] = wait(lambda: mhead() == h, 30) and cli("symbol", "foo", "--project", str(A)).returncode == 0
    time.sleep(3)
    res["decoy_never_called"] = not called.exists()

    # a failed build: the graph files cannot be written (the directory, the log and the lock stay writable)
    dk = A / ".devkb"
    vc("checkout", "-q", "main")
    wait(lambda: mhead() == head())
    time.sleep(2)
    ro = [f for f in dk.iterdir() if f.is_file() and f.suffix in (".json", ".jsonl", ".pkl")]
    for f in ro:
        f.chmod(0o444)
    commit("z.py", "def zed():\n    return 9\n", "z")
    time.sleep(6)
    for f in ro:
        f.chmod(0o644)
    out = cli("symbol", "foo", "--project", str(A))
    txt = (out.stdout + out.stderr).lower()
    res["failed_build_reported"] = bool(re.search(r"fail|exit(ed)? ?(code)? ?[1-9]|killed|crash", txt))
res["pass"] = all(res.values())
print(json.dumps(res))
