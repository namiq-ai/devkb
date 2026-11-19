import os, shutil, subprocess, sys
from pathlib import Path
src = Path(__file__).resolve().parents[1]
dst = Path(sys.argv[1])
if dst.exists():
    shutil.rmtree(dst)
top = {".venv", "corpus", "audit", ".bench-base", ".bench-arm.json"}
def ign(d, names):
    return [n for n in names if Path(d) == src and n in top]
shutil.copytree(src, dst, ignore=ign, symlinks=True)
print(subprocess.run(["git", "-C", str(dst), "status", "--short"], capture_output=True, text=True).stdout)
env = dict(os.environ, PYTHONPATH=str(dst))
print(subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(dst)], cwd=dst, env=env,
                     capture_output=True, text=True).stdout[-300:])
print(subprocess.run(["git", "-C", str(dst), "status", "--short"], capture_output=True, text=True).stdout)
