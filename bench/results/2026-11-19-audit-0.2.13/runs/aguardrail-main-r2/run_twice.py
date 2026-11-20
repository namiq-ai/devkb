import subprocess, sys, glob, os
names = sys.argv[1:] or sorted(os.path.basename(p)[:-3] for p in glob.glob("audit/repro/*.py") if not p.endswith("fx.py"))
for n in names:
    rcs = [subprocess.run([".venv/bin/python", f"audit/repro/{n}.py"], capture_output=True, text=True).returncode for _ in range(2)]
    print(n, rcs)
