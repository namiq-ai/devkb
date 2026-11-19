"""#214 (SPEC-DKB-007 S1) on a finished checkout: every decision line carries the search's intent and the graph question
asked, the stats count every action and intent, and the hook's decisions are unchanged.

Runs the checkout's own `scripts/devkb_guardrail.py` directly (the arm's registered hook may be another devkb's) on a
fixture repository (`compute` defined in pkg/core.py, called from pkg/app.py and tests/test_core.py, a docs/ page).
- `intents`: each case's log line has `intent` equal to the spec's §3.2 class;
- `questions`: and `question` equal to the graph question asked (`symbol --source`, `pack refactor`, `none`);
- `actions_unchanged`: each case's action is the one v0.2.12's hook took (S1 changes no answer);
- `stats`: `devkb guardrail-stats --log LOG` prints a count for read-answer and a table of intents.
Usage: 214.py CHECKOUT [--print-actions]
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
PRINT = "--print-actions" in sys.argv
# name, tool, input, intent, question, action at v0.2.12
CASES = [
    ("read_body", "Bash", {"command": 'grep -n "def compute" -A20 pkg/core.py'}, "read-body", "symbol --source", "read-answer"),
    ("locate", "Bash", {"command": 'grep -rn "def compute" pkg/'}, "locate", "symbol --source", "read-answer"),
    ("list_symbols", "Bash", {"command": 'grep -n "^def " pkg/core.py'}, "list-symbols", "pack refactor", "pass-through"),
    ("in_file", "Bash", {"command": "grep -n compute pkg/app.py"}, "in-file", "pack refactor", "alongside"),
    ("call_sites", "Bash", {"command": "grep -rn compute pkg/"}, "call-sites", "pack refactor", "substitute"),
    ("filtered", "Bash", {"command": "grep -rn compute . | grep -v tests"}, "call-sites-filtered", "pack refactor", "alongside"),
    ("count", "Bash", {"command": "grep -rc compute ."}, "count", "pack refactor", "alongside"),
    ("list_files", "Bash", {"command": "grep -rl compute ."}, "list-files", "pack refactor", "alongside"),
    ("invert", "Bash", {"command": "grep -rnv compute pkg/app.py"}, "invert", "pack refactor", "alongside"),
    ("non_code", "Bash", {"command": "grep -rn compute . --include=*.md"}, "non-code", "none", "pass-through"),
    ("grep_tool_body", "Grep", {"pattern": "def compute", "path": "pkg", "output_mode": "content", "-A": 10},
     "read-body", "symbol --source", "read-answer"),
    ("grep_tool_files", "Grep", {"pattern": "compute"}, "list-files", "pack refactor", "alongside"),
]
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg", A / "tests", A / "docs", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    files = {A / "pkg/__init__.py": "", A / "pkg/core.py": "def compute(x):\n    return x * 2\n\n\ndef other():\n    return 1\n",
             A / "pkg/app.py": "from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n",
             A / "tests/__init__.py": "",
             A / "tests/test_core.py": "from pkg.core import compute\n\n\ndef test_compute():\n    assert compute(2) == 4\n",
             A / "docs/guide.md": "# Guide\n\nCall compute to double a value.\n"}
    for p, t in files.items():
        p.write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env,
                   capture_output=True, timeout=600)
    hook = w / "scripts" / "devkb_guardrail.py"
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    intents, questions, actions, seen = {}, {}, {}, {}
    for i, (name, tool, inp, intent, question, action) in enumerate(CASES):
        sess = f"acc214-{name}"
        for j, t in enumerate(("Bash", tool)):     # the first call takes the session's reminder
            ev = {"session_id": sess, "tool_use_id": f"t{i}-{j}", "tool_name": t, "cwd": str(A),
                  "tool_input": {"command": "ls"} if j == 0 else inp}
            subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60)
        rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        mine = [r for r in rows if r.get("session") == sess and r.get("action") != "remind"]
        r = mine[-1] if mine else {}
        seen[name] = {k: r.get(k) for k in ("action", "intent", "question", "reason")}
        intents[name] = r.get("intent") == intent
        questions[name] = r.get("question") == question
        actions[name] = r.get("action") == action
    if PRINT:
        print(json.dumps(seen, indent=1))
    out["intents"], out["questions"], out["actions"] = intents, questions, actions
    st = subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "guardrail-stats", "--log", str(log)],
                        cwd=w, env=env, capture_output=True, text=True, timeout=120).stdout
    out["stats_text"] = st[-600:]
    out["stats"] = "read-answer" in st and "intent" in st.lower() and "read-body" in st
out["pass"] = all(out["intents"].values()) and all(out["questions"].values()) and all(out["actions"].values()) and out["stats"]
print(json.dumps({k: v for k, v in out.items() if k != "stats_text"} | {"stats_tail": out["stats_text"][-200:]}))
