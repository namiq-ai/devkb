"""#280: a definition search is answered in the shape its grep options ask for. Black box: the checkout's own PreToolUse hook
(scripts/devkb_guardrail.py) run on a fixture repository with a built graph; the shell's grep gives the reference output.
- locate_*: a search with no context option is not replaced by a body; whatever is returned is location lines only, or the
  search runs;
- after_*: `-A4` / `-A10` (the latter on a function over 80 lines) is either run, or its replacement carries every line grep
  prints;
- before_covers_asked_lines: `-B3` / `-B2` keeps the decorator and comment lines above the definition (or the search runs);
- second_defining_file_gets_body / every_defining_file_gets_body: a name defined in two files, searched in the second file or
  in both with -A, gets every body grep would print, with no false "end is not known" reason (or the search runs);
- callsite_not_answered_with_body: `grep -rn "helper(" pkg -A2` (call sites, not a definition pattern) is not answered with the
  definition's body (or the search runs)."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
LONG = "def longfn(x):\n" + "".join(f"    lv{i} = x + {i}\n" for i in range(100)) + "    return x\n"
TARGET = "import functools\n\n\n# cache every result\n@functools.lru_cache(maxsize=None)\ndef target(a):\n    b = a + 1\n    return b\n"
PK = "def helper(x):\n" + "".join(f"    v{i} = x + {i}\n" for i in range(20)) + "    return x\n"
files = {"m.py": TARGET, "long.py": LONG, "a.py": "def twin(x):\n    return x + 1\n",
         "b.py": "def twin(x):\n    y = x * 2\n    return y\n", "pkg/lib.py": PK,
         "pkg/use.py": "from pkg.lib import helper\n\n\ndef go():\n    return helper(1)\n"}

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    A, home = td / "repo", td / "home"
    (home / ".claude" / "hooks").mkdir(parents=True)
    for rel, t in files.items():
        (A / rel).parent.mkdir(parents=True, exist_ok=True)
        (A / rel).write_text(t)
    genv = dict(os.environ, GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@e.x", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@e.x")
    for c in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True, env=genv)
    py = str(W / ".venv/bin/python")
    if not Path(py).exists():
        py = "/home/namiq/orchestra/devkb/.venv/bin/python"
    if not Path(py).exists():
        py = sys.executable
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL="1")
    for k in ("DEVKB_GUARDRAIL_TEACH", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, timeout=600)
    n = [0]

    def hook(cmd):
        """(kind, text): kind 'deny', 'along' or 'none' (a reminder or nothing counts as none)."""
        n[0] += 1
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(A),
              "session_id": f"acc280-{n[0]}", "tool_use_id": f"t280-{n[0]}"}
        p = subprocess.run([py, "-P", str(W / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True,
                           text=True, env=env, cwd=A, timeout=120)
        if not p.stdout.strip():
            return "none", ""
        try:
            h = json.loads(p.stdout)["hookSpecificOutput"]
        except Exception:
            return "none", ""
        text = h.get("permissionDecisionReason") or h.get("additionalContext", "")
        if text.startswith("devkb guardrail:"):
            return "none", text
        kind = "deny" if h.get("permissionDecision") == "deny" else "along"
        if os.environ.get("DEBUG280"):
            print(f"[{kind}] {cmd}\n{text}\n", file=sys.stderr)
        return kind, text

    def grep(cmd):
        return subprocess.run(cmd, shell=True, cwd=A, capture_output=True, text=True).stdout

    def code_lines(real):
        out = []
        for ln in real.splitlines():
            m = re.match(r"^(?:[^:\n]+[:-])?\d+[:-](.*)$", ln)
            if m and m.group(1).strip():
                out.append(m.group(1).strip())
        return out

    def covers(cmd):
        """The search runs, or its replacement carries every line grep prints."""
        real = grep(cmd)
        kind, text = hook(cmd)
        if kind != "deny":
            return True
        return bool(real.strip()) and all(c in text for c in code_lines(real))

    cmd = 'grep -n "def target" m.py'
    kind, text = hook(cmd)
    res["locate_one_line"] = kind != "deny" or not any(s in text for s in ("b = a + 1", "return b"))
    kind, text = hook('grep -rn "def longfn" .')
    res["locate_long_function_no_body"] = kind != "deny" or ("lv50" not in text and "lv1 =" not in text)

    res["after_covers_asked_lines"] = covers('grep -n "def target" -A4 m.py')
    res["after_long_function_covers_asked_lines"] = covers('grep -n "def longfn" -A10 long.py')
    res["before_covers_asked_lines"] = covers('grep -n "def target" -B3 -A4 m.py') and covers('grep -n "def target" -B2 m.py')

    kind, text = hook('grep -n "def twin" -A5 b.py')
    res["second_defining_file_gets_body"] = kind != "deny" or ("return y" in text and "end is not known" not in text)
    res["every_defining_file_gets_body"] = covers('grep -n "def twin" -A3 a.py b.py')

    cmd = 'grep -rn "helper(" pkg -A2'
    kind, text = hook(cmd)
    res["callsite_not_answered_with_body"] = kind == "none" or ("v10 = x + 10" not in text and (kind != "deny" or covers(cmd)))
res["pass"] = all(res.values())
print(json.dumps(res))
