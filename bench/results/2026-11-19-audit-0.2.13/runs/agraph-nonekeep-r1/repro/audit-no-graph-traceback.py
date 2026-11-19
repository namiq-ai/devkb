import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _h

d = _h.make({"m.py": "def f():\n    pass\n"})
bad = []
for cmd in (["audit"], ["coverage"], ["query", "--about", "f"]):
    rc, out = _h.dk(cmd[0], "--project", d, *cmd[1:])
    one_line = len([l for l in out.strip().splitlines() if l.strip()]) == 1
    runnable = ("devkb build --project " + d) in out
    print(cmd, "rc", rc, "traceback" if "Traceback" in out else "", "one-line" if one_line else "multi-line",
          "runnable build hint" if runnable else "no runnable build hint")
    print("   ", out.strip().splitlines()[-1][:200])
    if "Traceback" in out or not one_line or not runnable:
        bad.append(cmd)
print("expected: every query command prints one line saying `devkb build --project <path>` first (as symbol/pack do)")
sys.exit(1 if bad else 0)
