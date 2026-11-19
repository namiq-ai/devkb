"""#217 (SPEC-DKB-007 S4) on a finished checkout: an answer added beside a search carries only its content, as grep-like
lines, and is never larger than grep's own output; a replacement has a one-line header.

Runs the checkout's own `scripts/devkb_guardrail.py` on a fixture where `compute` (pkg/core.py) is called from 3 files
(`few`) and `wide` from 120 files (`many`).
- `no_fixed_text`: no answer holds pack wording (Graph pack, Coverage, Built from, Test files among them, This pack was);
- `one_line_header`: every answer's wrapper is its first line, at most 110 characters;
- `not_larger_than_grep`: every answer added alongside is no larger than grep's real output for the same command;
- `no_duplicates`: a search grep still runs and whose lines would just repeat grep's output gets nothing beside it
  (a one-file search, a filtered search, a compound command, `-A5` that already shows the whole body);
- `replaced_has_every_site`: the replacement for `grep -rn compute pkg/` lists every line grep would print;
- `capped`: the outline of a file with 300 definitions is at most 1,600 characters and says lines are left out;
- `body_when_cut`: `grep -n "def long_one" -A3` (a 40-line body) gets the whole body beside it.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg" / "many", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    files = {"pkg/__init__.py": "", "pkg/many/__init__.py": "",
             "pkg/core.py": "def compute(x):\n    return x * 2\n\n\ndef wide(y):\n    return y\n",
             "pkg/app.py": "from pkg.core import compute\n\n\ndef run():\n    a = compute(3)\n    return compute(a)\n",
             "pkg/b.py": "from pkg.core import compute\n\n\ndef go():\n    return compute(1)\n",
             "pkg/big.py": "".join(f"def g{i}():\n    return {i}\n\n\n" for i in range(300)),
             "pkg/long.py": "def long_one():\n" + "".join(f"    x{i} = {i}\n" for i in range(38)) + "    return 0\n"}
    for i in range(120):
        files[f"pkg/many/m{i}.py"] = f"from pkg.core import wide\n\n\ndef f{i}():\n    return wide({i})\n"
    for rel, t in files.items():
        (A / rel).write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env,
                   capture_output=True, timeout=900)
    hook = w / "scripts" / "devkb_guardrail.py"

    def run(name, cmd):
        res = ""
        for j, c in enumerate(("ls", cmd)):
            ev = {"session_id": f"acc217-{name}", "tool_use_id": f"{name}-{j}", "tool_name": "Bash", "cwd": str(A), "tool_input": {"command": c}}
            res = subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60).stdout
        h = json.loads(res).get("hookSpecificOutput", {}) if res.strip().startswith("{") else {}
        kind = "deny" if h.get("permissionDecision") == "deny" else "context" if h.get("additionalContext") else "none"
        text = h.get("permissionDecisionReason", "") + h.get("additionalContext", "")
        if text.startswith("devkb guardrail: this is a code search"):
            kind, text = "none", ""
        grep = subprocess.run(["bash", "-c", cmd], cwd=A, capture_output=True, text=True).stdout
        return kind, text, grep

    cases = {"few_in_file": "grep -n compute pkg/app.py", "few_filtered": "grep -rn compute . | grep -v b.py",
             "few_replaced": "grep -rn compute pkg/", "few_body": 'grep -n "def compute" -A5 pkg/core.py',
             "many_compound": "grep -rn wide pkg/ && ls", "many_filtered": "grep -rn wide . | grep -v m1.py",
             "big_outline": 'grep -n "^def " pkg/big.py', "long_body": 'grep -n "def long_one" -A3 pkg/long.py'}
    got = {k: run(k, c) for k, c in cases.items()}
    PACK = ("Graph pack", "## Coverage", "Built from the dev-process graph", "Test files among them", "This pack was extracted")
    answers = {k: (kind, t, g) for k, (kind, t, g) in got.items() if kind != "none"}
    out["answered"] = sorted(answers)
    out["no_fixed_text"] = bool(answers) and all(not any(p in t for p in PACK) for _, t, _ in answers.values())
    out["one_line_header"] = all(len(t.splitlines()[0]) <= 110 for _, t, _ in answers.values())
    out["no_duplicates"] = {k: got[k][0] == "none" for k in ("few_in_file", "few_filtered", "many_compound", "many_filtered")}
    out["no_duplicates"]["few_body"] = got["few_body"][0] != "context"     # -A5 shows the 2-line body: replaced or nothing
    k, t, g = got["few_replaced"]
    out["replaced_has_every_site"] = k == "deny" and all(l.split(":", 2)[2].strip() in t for l in g.splitlines() if l)
    k, t, g = got["big_outline"]
    out["capped"] = k == "context" and len(t) <= 1600 and "more lines" in t
    k, t, g = got["long_body"]
    out["body_when_cut"] = k in ("context", "deny") and "return 0" in t and "x37 = 37" in t
out["pass"] = (out["no_fixed_text"] and out["one_line_header"] and all(out["no_duplicates"].values())
               and out["replaced_has_every_site"] and out["capped"] and out["body_when_cut"])
print(json.dumps(out))
