"""Shared helper for the repro scripts: build a fixture repo in a temp dir, run devkb on it."""
import os, subprocess, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.join(ROOT, ".venv", "bin", "python")


def make(files):
    d = tempfile.mkdtemp(prefix="devkbfx-")
    for p, t in files.items():
        fp = os.path.join(d, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(t)
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"], check=True)
    return d


def dk(d, *args, build=False):
    env = dict(os.environ, PYTHONPATH=ROOT, DEVKB_GUARDRAIL="0")
    cmd = [PY, "-m", "devkb.cli"] + list(args)
    r = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True)
    return (r.stdout + r.stderr), r.returncode


def build(d):
    return dk(d, "build", "--project", ".")
