import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scratch"))
from h import *

n = 800
files = {f"f{i}.py": "def run():\n    return 1\n" for i in range(n)}
files["u.py"] = "".join(f"def u{i}():\n    return run()\n" for i in range(n))
d = mk(files)
code = f'''
import sys, devkb.build_symbols as b
calls = [0]
orig = b._could_reach
def counted(*a, **k):
    calls[0] += 1
    return orig(*a, **k)
b._could_reach = counted
sys.argv = ["build_symbols", "--project", {d!r}]
b.main()
print("COUNT", calls[0])
'''
t = time.time()
r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True)
el = time.time() - t
cnt = int([l for l in r.stdout.splitlines() if l.startswith("COUNT")][-1].split()[1]) if "COUNT" in r.stdout else -1
print(f"{n} files each defining run() and {n} unresolved callers of run(): _could_reach called {cnt} times (n*n = {n*n}), {el:.1f}s")
print("expected: work proportional to the number of unresolved calls plus definitions (at most a few calls per pair-free lookup), here well under 50*n =", 50 * n)
sys.exit(1 if cnt > 50 * n else 0)
