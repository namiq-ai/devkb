import sys, os, shutil, hashlib, glob; sys.path.insert(0, "audit/scratch")
from h import *
import h
files = {}
for p in glob.glob("devkb/**/*.py", recursive=True) + glob.glob("scripts/*.py") + glob.glob("tests/*.py")[:40]:
    files[p] = open(p).read()
d = tempfile.mkdtemp(prefix="dkaudit")
subprocess.run(["git", "init", "-q", d])
for p, c in files.items():
    fp = os.path.join(d, p); os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, "w").write(c)
subprocess.run(["git", "-C", d, "add", "-A"])
res = []
for seed in ("1", "2", "3"):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    shutil.rmtree(os.path.join(d, ".devkb"), ignore_errors=True)
    r = subprocess.run([PY, "-m", "devkb.cli", "build", "--project", d], cwd=ROOT, env=env, capture_output=True, text=True)
    out = {}
    for f in sorted(os.listdir(os.path.join(d, ".devkb"))):
        fp = os.path.join(d, ".devkb", f)
        if os.path.isfile(fp) and f.endswith((".jsonl", ".json")):
            out[f] = hashlib.md5(open(fp, "rb").read()).hexdigest()
    res.append(out); print(seed, len(out))
for f in res[0]:
    print(f, [r.get(f) == res[0][f] for r in res])
