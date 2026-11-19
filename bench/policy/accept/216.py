"""#216 (SPEC-DKB-007 S3, with #171, #180, #181, #185) on a finished checkout: each search intent gets the graph question
that answers it, and nothing for counts, file lists, inverted and literal searches.

Runs the checkout's own `scripts/devkb_guardrail.py` directly on a fixture: `compute` and `helper` in pkg/core.py,
called from pkg/app.py and tests/test_core.py, mentioned in docs/guide.md; a TypeScript file web/a.ts.
Each case asserts the kind of answer (deny / context / none) and what its text holds or must not hold.
"""
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

w = Path(sys.argv[1]).resolve()
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "pkg", A / "tests", A / "docs", A / "web", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    files = {"pkg/__init__.py": "",
             "pkg/core.py": "def compute(x):\n    return x * 2\n\n\ndef helper(y):\n    return y\n",
             "pkg/app.py": "from pkg.core import compute, helper\n\n\ndef run():\n    a = compute(3)\n    return compute(a) + helper(1)\n",
             "tests/__init__.py": "",
             "tests/test_core.py": "from pkg.core import compute\n\n\ndef test_compute():\n    assert compute(2) == 4\n",
             "docs/guide.md": "# Guide\n\nCall compute to double a value.\n",
             "web/a.ts": "export function other(): number { return 1 }\n"}
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

    def run(name, tool, inp):
        sess = f"acc216-{name}"
        res = ""
        for j, (t, i) in enumerate((("Bash", {"command": "ls"}), (tool, inp))):
            ev = {"session_id": sess, "tool_use_id": f"{name}-{j}", "tool_name": t, "cwd": str(A), "tool_input": i}
            res = subprocess.run(["python3", str(hook)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60).stdout
        h = json.loads(res).get("hookSpecificOutput", {}) if res.strip().startswith("{") else {}
        if h.get("permissionDecision") == "deny":
            return "deny", h.get("permissionDecisionReason", "")
        ctx = h.get("additionalContext", "")
        return ("context" if ctx and "devkb guardrail: this is a code search" not in ctx else "none"), ctx

    B = lambda c: ("Bash", {"command": c})
    # name, call, kind wanted, must contain, must not contain
    cases = [
        ("read_body", B('grep -n "def compute" -A20 pkg/core.py'), "deny", ["return x * 2"], ["Graph pack"]),
        ("body_of_name", B("grep -n compute -A10 pkg/core.py"), "context", ["return x * 2"], ["Graph pack"]),
        ("locate_two", B('grep -n "def compute\\|def helper" pkg/core.py'), "context", ["pkg/core.py:1:", "pkg/core.py:5:"], ["Graph pack", "return x"]),
        ("list_symbols", B('grep -n "^def " pkg/core.py'), "context", ["compute", "helper", "L1-"], ["Graph pack"]),
        ("call_sites", B("grep -rn compute ."), "deny", ["pkg/app.py:5:", "tests/test_core.py:"], ["Graph pack", "more)"]),
        ("call_sites_tests", B("grep -rn compute tests/"), "deny", ["tests/test_core.py:"], ["pkg/app.py"]),
        ("in_file", B("grep -n compute pkg/app.py"), "context", ["5:", "6:"], ["Graph pack", "tests/", "pkg/core.py"]),
        ("filtered", B("grep -rn compute . | grep -v tests"), "context", ["pkg/app.py:5:"], ["tests/", "Graph pack"]),
        ("count", B("grep -rc compute ."), "none", [], []),
        ("list_files", B("grep -rl compute ."), "none", [], []),
        ("invert", B("grep -rnv compute pkg/app.py"), "none", [], []),
        ("literal", B('grep -rn "double a value" .'), "none", [], []),
        ("i180_count_after_context", B("grep -A3 -c 'def compute' pkg/core.py"), "none", [], []),
        ("i181_include_ts", B("grep -rn compute . --include=*.ts"), "none", [], []),
        ("i181_grep_glob_ts", ("Grep", {"pattern": "def compute", "glob": "**/*.ts", "output_mode": "content"}), "none", [], []),
        ("i185_two_e", B("grep -rn -e compute -e helper pkg/app.py"), "context", ["helper(1)", "compute(3)"], ["Graph pack"]),
    ]
    res = {}
    for name, (tool, inp), want, has, hasnt in cases:
        kind, text = run(name, tool, inp)
        res[name] = kind == want and all(x in text for x in has) and not any(x in text for x in hasnt)
        if not res[name]:
            out.setdefault("why", {})[name] = f"{kind}: {text[:160]!r}"
    # #171: a stale file gets no outline
    time.sleep(1)
    (A / "pkg" / "core.py").write_text(files["pkg/core.py"] + "\n\ndef added():\n    return 0\n")
    kind, text = run("stale_outline", *B('grep -n "^def " pkg/core.py'))
    res["stale_no_outline"] = kind == "none"
    out["cases"] = res
out["pass"] = all(out["cases"].values())
print(json.dumps(out))
