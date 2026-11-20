import sys, time, shutil; sys.path.insert(0, "audit/scratch")
from h import *
name = sys.argv[1]
d = tempfile.mkdtemp(prefix="dkaudit")
shutil.copytree(os.path.join(ROOT, "corpus", name), os.path.join(d, "r"), ignore=shutil.ignore_patterns(".git", ".devkb"))
r = os.path.join(d, "r")
subprocess.run(["git", "init", "-q", r]); subprocess.run(["git", "-C", r, "add", "-A"])
t = time.time(); print(build(r)[1][-200:], time.time() - t)
print(r)
for q in sys.argv[2:]:
    kind, n = q.split(":", 1)
    print("=====", q); print(dk("pack", "--project", r, kind, n)[1][:1800])
