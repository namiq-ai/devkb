import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
repo = root / "audit" / "_rp"
home = root / "audit" / "_home"
tool, arg = sys.argv[1], sys.argv[2]
inp = {"command": arg} if tool == "Bash" else json.loads(arg)
ev = {"tool_name": tool, "tool_input": inp, "cwd": str(repo), "session_id": "one" + str(os.getpid()), "tool_use_id": "u" + str(os.getpid())}
env = dict(os.environ, HOME=str(home), DEVKB_GUARDRAIL="1", DEVKB_GUARDRAIL_TEACH="1", PYTHONPATH=str(repo))
p = subprocess.run([sys.executable, "-P", str(repo / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=repo)
print("rc", p.returncode, "env", {k: v for k, v in os.environ.items() if k.startswith("DEVKB")})
print(p.stdout, p.stderr[-800:])
