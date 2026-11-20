import sys, os, subprocess, re
sys.path.insert(0, os.path.dirname(__file__))
import fx

body = "def helper(x):\n    return x * 2\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(3))
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": body})
sub = root / "pkg"
# the agent works from a subdirectory of the repository (its cwd), as agents do
dec, text = fx.hook(sub, {"command": "grep -rn helper ."})
print("decision:", dec)
print(text)
m = re.search(r"`(devkb [^`]+)`", text)
if not m:
    print("no teach line in the answer (cannot judge)")
    sys.exit(0)
cmd = m.group(1).split()
env = dict(os.environ, PYTHONPATH=str(fx.ROOT), PYTHONWARNINGS="ignore")
p = subprocess.run([str(fx.ROOT / ".venv/bin/python"), "-m", "devkb.cli", *cmd[1:]], cwd=sub, capture_output=True, text=True, env=env)
out = (p.stdout + p.stderr).strip()
print("running the suggested command from", sub.name, "->", out[:200])
if p.returncode != 0 or "no graph" in out.lower() or "not found" in out.lower() or "helper" not in out:
    print("DEFECT: the suggested `--project .` command does not work from the directory the search ran in")
    sys.exit(1)
print("ok")
