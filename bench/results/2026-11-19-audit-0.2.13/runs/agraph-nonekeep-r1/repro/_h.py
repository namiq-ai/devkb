"""Shared helper for repro scripts: build a fixture in a temp dir, run devkb."""
import os, subprocess, sys, tempfile, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = os.path.join(ROOT, ".venv", "bin", "python")


def make(files):
    d = tempfile.mkdtemp(prefix="dkaudit-")
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(textwrap.dedent(body))
    env = dict(os.environ, GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@b",
               GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@b")
    subprocess.run(["git", "init", "-q", d], env=env)
    subprocess.run(["git", "-C", d, "add", "-A"], env=env)
    subprocess.run(["git", "-C", d, "commit", "-qm", "i"], env=env)
    return d


def dk(*args, cwd=None):
    env = dict(os.environ, PYTHONPATH=ROOT, DEVKB_GUARDRAIL="0")
    r = subprocess.run([PY, "-m", "devkb.cli", *args], capture_output=True,
                       text=True, cwd=cwd or ROOT, env=env)
    return r.returncode, r.stdout + r.stderr


def build(d):
    return dk("build", "--project", d)
