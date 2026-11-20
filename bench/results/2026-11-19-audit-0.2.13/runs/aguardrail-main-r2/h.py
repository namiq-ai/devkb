"""helper: python audit/h.py 'grep -rn foo .'  -> hook output"""
import json, subprocess, os, sys, tempfile
R = os.getcwd()
home = tempfile.mkdtemp()
for n, c in enumerate(sys.argv[1:]):
    if c.startswith("G:"):
        ev = {"tool_name": "Grep", "tool_input": json.loads(c[2:])}
    else:
        ev = {"tool_name": "Bash", "tool_input": {"command": c}}
    ev.update(cwd=R, session_id="s%d" % n, tool_use_id="t%d" % n)
    p = subprocess.run([R + '/.venv/bin/python', 'scripts/devkb_guardrail.py'], input=json.dumps(ev), capture_output=True,
                       text=True, env=dict(os.environ, HOME=home))
    print("=== ", c)
    if p.stdout.strip():
        h = json.loads(p.stdout)["hookSpecificOutput"]
        print(h.get("permissionDecision"), "\n", h.get("additionalContext") or h.get("permissionDecisionReason"))
    print(p.stderr[-300:])
