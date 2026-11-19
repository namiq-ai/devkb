import sys, time, cProfile, pstats; sys.path.insert(0, "audit/scratch")
from h import *
n = 1200
f = {f"f{i}.py": "def run():\n    return 1\n" for i in range(n)} | {"u.py": "".join(f"def u{i}():\n    return run()\n" for i in range(n))}
d = mk(f)
r = subprocess.run([PY, "-m", "cProfile", "-o", "/tmp/prof.out", "-m", "devkb.cli", "build", "--project", d], cwd=ROOT, capture_output=True, text=True)
p = pstats.Stats("/tmp/prof.out"); p.sort_stats("cumulative").print_stats(18)
