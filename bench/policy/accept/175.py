"""#175 on a finished checkout: a search for a string key the graph records (#148) gets the key's writes and reads by
function beside grep; a name that is neither a symbol nor a key still passes through.

Runs the checkout's own `scripts/devkb_guardrail.py` on a fixture: `unresolved_files` is a dict key written in
pkg/report.py::collect and read in collect and show; `nothing_here` appears only in a comment.
- `key_alongside`: `grep -rn unresolved_files pkg/` gets added context (not a replacement) naming collect and show, with
  writes and reads by line;
- `key_logged`: its log line has action alongside and reason `key`;
- `neither_passes`: `grep -rn nothing_here pkg/` gets no devkb answer.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
REPORT = ('def collect(files):\n    out = {"unresolved_files": [], "seen": 0}\n    for f in files:\n'
          '        out["unresolved_files"].append(f)\n    return out\n\n\n'
          'def show(r):\n    # nothing_here\n    return len(r["unresolved_files"])\n')
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    (A / "pkg" / "__init__.py").write_text("")
    (A / "pkg" / "report.py").write_text(REPORT)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env,
                   capture_output=True, timeout=600)
    hook = w / "scripts" / "devkb_guardrail.py"
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"

    def run(name, cmd):
        sess = f"acc175-{name}"
        res = ""
        for j, c in enumerate(("ls", "grep -rn zz_warmup .", cmd)):    # the session's reminder is taken first
            ev = {"session_id": sess, "tool_use_id": f"{name}-{j}", "tool_name": "Bash", "cwd": str(A), "tool_input": {"command": c}}
            res = subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60).stdout
        h = json.loads(res).get("hookSpecificOutput", {}) if res.strip().startswith("{") else {}
        kind = "deny" if h.get("permissionDecision") == "deny" else "context" if h.get("additionalContext") else "none"
        text = h.get("permissionDecisionReason", "") + h.get("additionalContext", "")
        if "devkb guardrail: this is a code search" in text:
            kind, text = "none", ""
        rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        mine = [r for r in rows if r.get("session") == sess and r.get("action") != "remind"]
        return kind, text, (mine[-1] if mine else {})

    kind, text, row = run("key", "grep -rn unresolved_files pkg/")
    out["key_alongside"] = (kind == "context" and "collect" in text and "show" in text and "writes L2" in text
                            and "reads L4" in text and "L10" in text)
    out["key_logged"] = row.get("action") == "alongside" and row.get("reason") == "key"
    kind, text, row = run("neither", "grep -rn nothing_here pkg/")
    out["neither_passes"] = kind == "none"
out["pass"] = out["key_alongside"] and out["key_logged"] and out["neither_passes"]
print(json.dumps(out))
