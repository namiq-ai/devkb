import sys, os, tempfile; sys.path.insert(0, "audit")
from probe import *
d = tempfile.mkdtemp(prefix="dk_empty_")
write(d, {"a.py": "def f():\n    pass\n"})
subprocess.run(["git", "init", "-q"], cwd=d)
for c in ["symbol x", "outline a.py", "uses x", "docs x", "pack change x", "pack refactor x", "pack file a.py",
          "pack error x", "query --about x", "audit", "coverage", "stats", "misses", "mcp --help"]:
    rc, out = devkb(d, *c.split())
    print("==", c, rc, "TRACEBACK" if "Traceback" in out else "", out.strip().splitlines()[-1:] )
