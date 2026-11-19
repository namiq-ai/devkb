import glob, subprocess, sys, os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for f in sorted(glob.glob(os.path.join(root, "audit/repro/*.py"))):
    codes = [subprocess.run([root + "/.venv/bin/python", f], capture_output=True).returncode for _ in range(2)]
    print(os.path.basename(f), codes)
