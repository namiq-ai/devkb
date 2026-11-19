import sys, time; sys.path.insert(0, "audit/scratch")
from h import *

def timed(files):
    d = mk(files); t = time.time(); rc, out = build(d); return time.time() - t, out[-100:]

for n in (200, 400, 800):
    f = {}
    for i in range(n):
        f[f"m{i}.py"] = f"class A{i}:\n    def go(self):\n        return 1\ndef f{i}():\n    a = A{i}()\n    return a.go()\n"
    print("typed receivers", n, timed(f)[0])
for n in (5000, 10000, 20000):
    body = "".join(f"C{i} = {i}\n" for i in range(n)) + "def f():\n    return C1 + C5\n"
    print("consts", n, timed({"m.py": body})[0])
# many functions in one file, many calls
for n in (2000, 4000, 8000):
    body = "".join(f"def f{i}():\n    return f{(i+1)%n}()\n" for i in range(n))
    print("chain", n, timed({"m.py": body})[0])
# many constant reads
for n in (1000, 2000, 4000):
    body = "".join(f"C{i} = {i}\n" for i in range(n)) + "".join(f"def g{i}():\n    return C{i} + C{(i+1)%n}\n" for i in range(n))
    print("constreads", n, timed({"m.py": body})[0])
for n in (1000, 2000, 4000):
    body = "def f():\n    d = {}\n" + "".join(f"    d['k{i}'] = d.get('k{i}')\n" for i in range(n))
    print("stringkeys", n, timed({"m.py": body})[0])
