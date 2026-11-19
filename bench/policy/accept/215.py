"""#215 (SPEC-DKB-007 S2) on a finished checkout: a keyword or a word in another case is never answered as a symbol,
alternation is read per grep dialect, and option values are never the pattern.

Runs the checkout's own `scripts/devkb_guardrail.py` directly on a fixture: `compute` and `helper` in pkg/core.py,
called from pkg/app.py; `class Def` in pkg/model.py, used in pkg/app.py; `READ_ANSWER` in pkg/flags.py.
- `no_text`: no devkb answer (deny or added context naming a symbol) for `Compute`, `COMPUTE`, `^def `, `read_answer`,
  BRE `compute|helper`, `-F 'compute\\|helper'` (#184, #186);
- `answered`: an answer for `-i COMPUTE` (case-insensitive), `-E 'compute|helper'`, BRE `compute\\|helper`, and the plain
  `grep -rn compute pkg/` (unchanged);
- `pattern_not_option_value`: the logged names are ["compute"] for `-A 30`, `-m 5`, `rg -t py` and `--include '*.py'`.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    files = {"pkg/__init__.py": "",
             "pkg/core.py": "def compute(x):\n    return x * 2\n\n\ndef helper(y):\n    return y\n",
             "pkg/model.py": "class Def:\n    pass\n",
             "pkg/flags.py": "READ_ANSWER = 1\n",
             "pkg/app.py": "from pkg.core import compute, helper\nfrom pkg.model import Def\nfrom pkg.flags import READ_ANSWER\n\n\n"
                           "def run():\n    d = Def()\n    return compute(3) + helper(READ_ANSWER)\n"}
    for rel, t in files.items():
        (A / rel).write_text(t)
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
        sess = f"acc215-{name}"
        res = ""
        for j, c in enumerate(("ls", cmd)):
            ev = {"session_id": sess, "tool_use_id": f"{name}-{j}", "tool_name": "Bash", "cwd": str(A), "tool_input": {"command": c}}
            res = subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60).stdout
        h = json.loads(res).get("hookSpecificOutput", {}) if res.strip().startswith("{") else {}
        text = h.get("permissionDecisionReason", "") + h.get("additionalContext", "")
        rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        mine = [r for r in rows if r.get("session") == sess and r.get("action") != "remind"]
        return text, (mine[-1] if mine else {})

    answer = lambda t: any(m in t for m in ("Graph pack", "devkb answered", "devkb's answer"))   # any devkb answer wrapper
    no_text = {n: not answer(run(n, c)[0]) for n, c in [
        ("Compute", "grep -rn Compute ."), ("COMPUTE", "grep -rn COMPUTE ."), ("def_only", 'grep -n "^def " pkg/core.py'),
        ("read_answer", "grep -c read_answer pkg/flags.py"), ("bre_bar", "grep -rn 'compute|helper' ."),
        ("fixed", "grep -rnF 'compute\\|helper' .")]}
    answered = {n: answer(run(n, c)[0]) for n, c in [
        ("i_COMPUTE", "grep -rni COMPUTE ."), ("ere_bar", "grep -rnE 'compute|helper' ."),
        ("bre_alt", "grep -rn 'compute\\|helper' ."), ("plain", "grep -rn compute pkg/")]}
    values = {n: run(n, c)[1].get("names") == ["compute"] for n, c in [
        ("A30", "grep -n -A 30 compute pkg/app.py"), ("m5", "grep -m 5 -rn compute ."), ("rg_t", "rg -t py compute"),
        ("include", "grep -rn --include '*.py' compute .")]}
    out.update(no_text=no_text, answered=answered, pattern_not_option_value=values)
out["pass"] = all(out["no_text"].values()) and all(out["answered"].values()) and all(out["pattern_not_option_value"].values())
print(json.dumps(out))
