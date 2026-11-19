import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
repo = root / "audit" / "_rp"
home = root / "audit" / "_home"
n = 0
for cmd in sys.argv[1:]:
    n += 1
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(repo), "session_id": f"m{os.getpid()}-{n}", "tool_use_id": f"m{os.getpid()}-{n}"}
    env = dict(os.environ, HOME=str(home), DEVKB_GUARDRAIL="1", DEVKB_GUARDRAIL_TEACH="1", PYTHONPATH=str(repo))
    p = subprocess.run([sys.executable, "-P", str(repo / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=repo)
    g = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True)
    print("=" * 70, "\nCMD:", cmd, "\nGREP prints", len(g.stdout.splitlines()), "lines /", len(g.stdout), "chars")
    if p.stdout.strip():
        h = json.loads(p.stdout)["hookSpecificOutput"]
        a = h.get("permissionDecisionReason") or h.get("additionalContext")
        print("HOOK", "DENY" if h.get("permissionDecision") == "deny" else "ALONG", len(a), "chars,", len(a.splitlines()), "lines\n" + a[:1500])
    else:
        print("HOOK: nothing", p.stderr[-200:])
