import subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for f in sorted((root / "audit" / "repro").glob("[a-z]*.py")):
    rc = [subprocess.run([sys.executable, str(f)], capture_output=True, text=True).returncode for _ in range(2)]
    print(f.name, rc)
