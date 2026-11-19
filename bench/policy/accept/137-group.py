"""#137 with #138 on a finished checkout: a graph miss from a search of one file is recorded with that file's name, and
each match names the function that holds it, also under a header that spans several lines.

Runs the checkout's own PreToolUse and PostToolUse hooks (scripts/devkb_guardrail.py, scripts/devkb_guardrail_post.py)
on a fixture where `helper` is defined twice (static in src/a.c and src/b.c; in pkg/one.py and pkg/two.py), so devkb
cannot answer and a miss is due; callers have headers over several lines (`static int\\ncaller_c(int x,\\n int y)`,
`def caller_py(\\n a,\\n):`).
- `one_file`: `grep -rn helper src/a.c` (output `line:text`) records matches named `src/a.c:N`;
- `one_file_with_options`: `grep -n -A2 helper src/a.c` and `grep -m 5 -n helper src/a.c` do the same;
- `one_file_grep_tool` (reported, not required: the ticket asks for grep commands): the Grep tool on path src/a.c does the same;
- `enclosing_c`: in `grep -rn helper src/` the call inside caller_c is `in: caller_c`;
- `enclosing_py`: in `grep -rn helper pkg/` the call inside caller_py is `in: caller_py`.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
C_A = ("static int\nhelper(int x,\n       int y)\n{\n    return x + y;\n}\n\n"
       "static int\ncaller_c(int x,\n         int y)\n{\n    int z = x;\n    return helper(z, y);\n}\n")
C_B = "static int helper(int x, int y)\n{\n    return x - y;\n}\n"
PY_ONE = "def helper(a):\n    return a\n\n\ndef caller_py(\n    a,\n):\n    b = a\n    return helper(b)\n"
PY_TWO = "def helper(a):\n    return -a\n"
out = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A / "src", A / "pkg", home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    for rel, t in {"src/a.c": C_A, "src/b.c": C_B, "pkg/__init__.py": "", "pkg/one.py": PY_ONE, "pkg/two.py": PY_TWO}.items():
        (A / rel).write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(w), PYTHONWARNINGS="ignore", PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([str(w / ".venv/bin/python"), "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env,
                   capture_output=True, timeout=600)
    pre, post = w / "scripts" / "devkb_guardrail.py", w / "scripts" / "devkb_guardrail_post.py"
    log = A / ".devkb" / "graph-misses.jsonl"
    n = [0]

    def miss(tool, inp, output):
        """The miss line written for one search, or {}."""
        n[0] += 1
        sess = f"acc137-{n[0]}"
        before = len(log.read_text().splitlines()) if log.exists() else 0
        for j, (t, i) in enumerate((("Bash", {"command": "ls"}), (tool, inp))):
            ev = {"session_id": sess, "tool_use_id": f"u{n[0]}-{j}", "tool_name": t, "cwd": str(A), "tool_input": i}
            subprocess.run(["python3", str(pre)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=60)
        ev = {"session_id": sess, "tool_use_id": f"u{n[0]}-1", "tool_name": tool, "cwd": str(A), "tool_input": inp,
              "tool_response": {"stdout": output} if tool == "Bash" else {"content": output, "mode": "content"}}
        subprocess.run(["python3", str(post)], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=A, timeout=120)
        rows = log.read_text().splitlines()[before:] if log.exists() else []
        return json.loads(rows[-1]) if rows else {}

    def sh(cmd):
        return subprocess.run(["bash", "-c", cmd], cwd=A, capture_output=True, text=True).stdout

    def at(row):
        return [m["at"] for m in (row.get("grep") or {}).get("matches", [])]

    def one_file_ok(row):
        return bool(at(row)) and all(a.startswith("src/a.c:") for a in at(row)) and "src/a.c:13" in at(row)

    cmd = "grep -rn helper src/a.c"
    out["one_file"] = one_file_ok(miss("Bash", {"command": cmd}, sh(cmd)))
    opts = {}
    for c in ("grep -n -A2 helper src/a.c", "grep -m 5 -n helper src/a.c"):
        opts[c] = one_file_ok(miss("Bash", {"command": c}, sh(c)))
    out["one_file_with_options"] = opts
    out["one_file_grep_tool"] = one_file_ok(miss("Grep", {"pattern": "helper", "path": "src/a.c", "output_mode": "content", "-n": True},
                                                sh("grep -n helper src/a.c")))
    cmd = "grep -rn helper src/"
    r = miss("Bash", {"command": cmd}, sh(cmd))
    ins = {m["at"]: m["in"] for m in (r.get("grep") or {}).get("matches", [])}
    out["enclosing_c"] = ins.get("src/a.c:13") == "caller_c"
    cmd = "grep -rn helper pkg/"
    r = miss("Bash", {"command": cmd}, sh(cmd))
    ins = {m["at"]: m["in"] for m in (r.get("grep") or {}).get("matches", [])}
    out["enclosing_py"] = ins.get("pkg/one.py:9") == "caller_py"
# one_file_grep_tool is reported, not required: the ticket asks for grep commands (parse_grep, bash_pattern); the Grep
# tool on one file is this branch's extension
out["pass"] = (out["one_file"] and all(out["one_file_with_options"].values())
               and out["enclosing_c"] and out["enclosing_py"])
print(json.dumps(out))
