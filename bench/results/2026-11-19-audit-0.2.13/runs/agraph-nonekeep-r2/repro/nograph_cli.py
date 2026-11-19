import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({"m.py": "def f():\n    return 1\n"})
bad = False
for args in (["audit", "--project", "."], ["query", "--project", ".", "--about", "f"], ["coverage", "--project", "."]):
    out, rc = _fx.dk(d, *args)
    ok = "Traceback" not in out and "devkb build" in out
    print(args[0], "rc", rc, "OK" if ok else "BAD: traceback or no `devkb build` hint")
    print("   ", out.strip().splitlines()[-1][:200])
    bad |= not ok
print("expected: one line 'no devkb graph ... run `devkb build --project ...` first' for every command (as symbol/pack give)")
sys.exit(1 if bad else 0)
