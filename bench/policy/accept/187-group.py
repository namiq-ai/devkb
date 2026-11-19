"""#187 with #191 on a finished checkout: a definition search devkb cannot answer (one file, or with -A) still writes
its pending miss record and logs the real reason; a definition answer from a subfolder shows the path grep prints.

Runs the checkout's own `scripts/devkb_guardrail.py` on a fixture (`compute` in pkg/core.py, called from pkg/app.py):
- `one_file_miss`: `grep -n 'def late_only' pkg/core.py` passes through, writes its pending record, and its reason is
  not the hard-coded `not-recursive`;
- `context_miss`: the same for `grep -rn -A3 'def late_only' .`;
- `subdir_path`: from cwd pkg/, `grep -rn 'def compute' .` is answered with a location relative to pkg/ (`./core.py:1:`
  or `core.py:1:`) or absolute, never `pkg/core.py:1:`.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    for rel, t in {"pkg/__init__.py": "", "pkg/core.py": "def compute(x):\n    return x * 2\n",
                   "pkg/app.py": "from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n"}.items():
        (A / rel).write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env,
                   capture_output=True, timeout=600)
    hook = w / "scripts" / "devkb_guardrail.py"
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"

    def run(name, cwd, cmd):
        res = ""
        for j, c in enumerate(("ls", cmd)):
            ev = {"session_id": f"acc187-{name}", "tool_use_id": f"{name}-{j}", "tool_name": "Bash", "cwd": str(cwd),
                  "tool_input": {"command": c}}
            res = subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env,
                                 cwd=cwd, timeout=60).stdout
        h = json.loads(res).get("hookSpecificOutput", {}) if res.strip().startswith("{") else {}
        rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        mine = [r for r in rows if r.get("session") == f"acc187-{name}" and r.get("action") != "remind"]
        pending = home / ".claude" / "hooks" / ".devkb-guardrail-pending" / f"{name}-1"
        return h.get("permissionDecisionReason", "") + h.get("additionalContext", ""), (mine[-1] if mine else {}), pending.exists()

    for name, cmd in (("one_file_miss", "grep -n 'def late_only' pkg/core.py"), ("context_miss", "grep -rn -A3 'def late_only' .")):
        _, row, pending = run(name, A, cmd)
        out[name] = row.get("action") == "pass-through" and pending and row.get("reason") not in (None, "not-recursive")
        out[name + "_seen"] = {"action": row.get("action"), "reason": row.get("reason"), "pending": pending}
    text, row, _ = run("subdir_path", A / "pkg", "grep -rn 'def compute' .")
    first = next((l for l in text.splitlines() if ":1:" in l), "")
    out["subdir_path"] = bool(first) and "pkg/core.py:1:" not in first and (
        first.startswith(("./core.py:1:", "core.py:1:")) or first.startswith(str(A / "pkg" / "core.py") + ":1:"))
    out["subdir_seen"] = first[:80]
out["pass"] = out["one_file_miss"] and out["context_miss"] and out["subdir_path"]
print(json.dumps(out))
