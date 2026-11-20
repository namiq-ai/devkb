import sys, os, subprocess, tempfile, hashlib, shutil, json; sys.path.insert(0, "audit")
from probe import *
files = {"a.py": "from celery import shared_task\n@shared_task\ndef job():\n" + "".join("    f%d()\n" % i for i in range(30)) +
         "".join("def f%d():\n    g%d()\n    h()\ndef g%d():\n    h()\n    f0() if False else None\n" % (i, i, i) for i in range(30)) +
         "def h():\n    pass\n"}
d, _ = build(files)
res = []
for seed in ("1", "2", "3", "4"):
    shutil.rmtree(d + "/.devkb", ignore_errors=True)
    env = dict(os.environ, PYTHONHASHSEED=seed)
    p = subprocess.run([PY, "-m", "devkb.cli", "build", "--project", d], cwd=ROOT, env=env, capture_output=True, text=True)
    h = {}
    for f in sorted(os.listdir(d + "/.devkb")):
        fp = os.path.join(d + "/.devkb", f)
        if f.endswith((".jsonl",)):
            h[f] = hashlib.md5(open(fp, "rb").read()).hexdigest()[:6]
    res.append(h)
    print(seed, p.stdout.strip()[-80:])
for f in res[0]:
    print(f, [o.get(f) for o in res])
