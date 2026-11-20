import sys, time; sys.path.insert(0, "audit/scratch")
from h import *
for n in (400, 800, 1600):
    f = {f"f{i}.py": "def run():\n    return 1\n" for i in range(n)} | {"u.py": "".join(f"def u{i}():\n    return run()\n" for i in range(n))}
    d = mk(f); t = time.time(); rc, out = build(d); print(n, round(time.time() - t, 2), out.strip().splitlines()[-1][-80:], flush=True)
