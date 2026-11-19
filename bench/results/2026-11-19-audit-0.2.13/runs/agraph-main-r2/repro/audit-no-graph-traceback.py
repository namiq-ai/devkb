import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import write, devkb

d = tempfile.mkdtemp(prefix="dk_nograph_")
write(d, {"a.py": "def f():\n    pass\n"})
bad = []
for cmd in (["audit"], ["coverage"], ["query", "--about", "x"]):
    rc, out = devkb(d, *cmd)
    print("$ devkb", " ".join(cmd), "-> rc", rc)
    print(out)
    if "Traceback" in out:
        bad.append(cmd[0])
    if "build.py" in out and not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "devkb", "build.py")):
        bad.append(cmd[0] + "(names missing devkb/build.py)")
if bad:
    print("DEFECT: no-graph errors that are a traceback or name a script that does not exist:", bad)
    print("EXPECTED: one line: no devkb graph ...: run `devkb build --project <path>` first")
    sys.exit(1)
print("ok")
