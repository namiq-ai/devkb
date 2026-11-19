"""#182 on a finished checkout: a graph that has not seen the working tree's code never replaces a search.

Runs the checkout's own `scripts/devkb_guardrail.py` on a fixture (`compute` in pkg/core.py, called from pkg/app.py),
graph built, then pkg/late.py added untracked with a new caller and a second `def compute`:
- `fresh_replaces`: before the change, `grep -rn compute .` is replaced (the fix keeps the saving);
- `untracked_no_replace`: after it, neither `grep -rn compute .` nor `grep -rn 'def compute' .` is replaced;
- `committed_no_replace`: after committing it (graph at an older commit), `grep -rn compute .` is not replaced.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    (A / "pkg").mkdir(parents=True)
    (home / ".claude" / "hooks").mkdir(parents=True)
    (A / "pkg/__init__.py").write_text("")
    (A / "pkg/core.py").write_text("def compute(x):\n    return x * 2\n")
    (A / "pkg/app.py").write_text("from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n")
    subprocess.run("git init -q && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=A, check=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, timeout=600)
    n = [0]

    def denied(cmd):
        n[0] += 1
        out = ""
        for j, c in enumerate(("ls", cmd)):
            ev = {"session_id": f"acc182-{n[0]}", "tool_use_id": f"t{n[0]}-{j}", "tool_name": "Bash", "cwd": str(A), "tool_input": {"command": c}}
            out = subprocess.run(["python3", str(w / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True,
                                 text=True, env=env, cwd=A, timeout=60).stdout
        h = json.loads(out).get("hookSpecificOutput", {}) if out.strip().startswith("{") else {}
        return h.get("permissionDecision") == "deny"

    out = {"fresh_replaces": denied("grep -rn compute .")}
    (A / "pkg/late.py").write_text("from pkg.core import compute\n\n\ndef go():\n    return compute(9)\n\n\ndef compute(z):\n    return z\n")
    out["untracked_no_replace"] = not denied("grep -rn compute .") and not denied("grep -rn 'def compute' .")
    subprocess.run("git add -A && git -c user.name=t -c user.email=t@example.com commit -qm late", shell=True, cwd=A, check=True)
    out["committed_no_replace"] = not denied("grep -rn compute .")
out["pass"] = all(out.values())
print(json.dumps(out))
