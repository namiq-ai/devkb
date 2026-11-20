import os, subprocess, sys, tempfile, textwrap
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.join(ROOT, ".venv/bin/python")


def mk(files):
    d = tempfile.mkdtemp(prefix="dkaudit")
    subprocess.run(["git", "init", "-q", d])
    for p, c in files.items():
        fp = os.path.join(d, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "w").write(textwrap.dedent(c))
    subprocess.run(["git", "-C", d, "add", "-A"])
    return d


def dk(*a):
    r = subprocess.run([PY, "-m", "devkb.cli", *a], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def build(d):
    return dk("build", "--project", d)
