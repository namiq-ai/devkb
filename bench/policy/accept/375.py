"""#375: the teach line reaches the agent when devkb has the complete answer, not only when the hook adds one. Black box: the
checkout's own PreToolUse hook (scripts/devkb_guardrail.py) on a fixture repository with a built graph and no MCP server.
- dup_infile_teaches: `grep -n helper pkg/use.py` (helper Complete; grep prints the same lines) runs, and the hook adds only
  a line naming `devkb uses helper`; nothing else, under 120 characters, no answer lines;
- dup_readbody_teaches: `grep -rn -A8 helper pkg/` (the context shows helper's whole body) likewise names
  `devkb symbol helper --source` (corrected after the arms ran: the first version used a definition search with context in one
  file, which is #358's case, not a duplicate);
- dup_not_denied: neither search is replaced;
- teach_once_per_command: the same command again in the same session adds nothing;
- teach_off: with DEVKB_GUARDRAIL_TEACH=0 the duplicate adds nothing;
- span_hint_teaches: `sed -n 1,3p pkg/long.py`, which stops inside `long_one`, names `devkb symbol long_one --source`;
- reminder_no_mcp_no_log: the reminder names a devkb command and, with no MCP server configured, neither `mcp__devkb` nor a
  dogfood log;
- off_by_default: without DEVKB_GUARDRAIL_TEACH_ALL=1 a duplicate adds nothing. The owner's decision after the keep-or-drop
  benchmark (17 teach lines seen against 7, 0 direct devkb queries in both arms, +12.6% cost): the teach checks above run
  with the setting on (revised 2026-11-20)."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
LONG = "def long_one(x):\n" + "".join(f"    v{i} = x + {i}\n" for i in range(12)) + "    return x\n"
files = {
    "pkg/__init__.py": "",
    "pkg/lib.py": "def helper(x):\n    total = x + 1\n    return total\n",
    "pkg/use.py": "from pkg.lib import helper\n\n\ndef go():\n    r = helper(3)\n    return helper(r)\n",
    "pkg/long.py": LONG,
}

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
        py = "/home/namiq/orchestra/ip/devkb/.venv/bin/python"
    if not Path(py).exists():
        py = sys.executable
    base_env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL="1",
                    DEVKB_GUARDRAIL_TEACH_ALL="1")
    for k in ("DEVKB_GUARDRAIL_TEACH", "DEVKB_TELEMETRY", "DEVKB_MISSLOG", "DEVKB_GUARDRAIL_KEEP", "DEVKB_GUARDRAIL_OUTLINE"):
        base_env.pop(k, None)
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=base_env, capture_output=True, timeout=600)
    n = [0]

    def hook(cmd, session=None, **extra):
        """(deny?, every text the hook added) for one Bash PreToolUse event."""
        n[0] += 1
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(A),
              "session_id": session or f"acc375-{n[0]}", "tool_use_id": f"t375-{n[0]}"}
        p = subprocess.run([py, "-P", str(W / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True,
                           text=True, env=dict(base_env, **extra), cwd=A, timeout=120)
        if not p.stdout.strip():
            return False, ""
        try:
            h = json.loads(p.stdout)["hookSpecificOutput"]
        except Exception:
            return False, ""
        if os.environ.get("DEBUG375"):
            print(f"--- {cmd}\n{json.dumps(h)}\n", file=sys.stderr)
        return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason") or h.get("additionalContext", "")

    def warm(session):
        """Spend the session's one reminder on an unrelated search first, so the next answer is the hook's own."""
        hook('grep -rn "def nosuchname_q" pkg/', session=session)

    def only_teach(text, command):
        lines = [x for x in text.strip().splitlines() if x.strip()]
        return (len(lines) == 1 and command in lines[0] and len(lines[0]) < 120
                and not re.search(r"pkg/\w+\.py:\d+", text) and "helper(3)" not in text)

    s = "acc375-infile"
    warm(s)
    deny1, t1 = hook("grep -n helper pkg/use.py", session=s)
    res["dup_infile_teaches"] = only_teach(t1, "devkb uses helper")
    deny2, t2 = hook("grep -n helper pkg/use.py", session=s)
    res["teach_once_per_command"] = bool(t1) and not t2

    s = "acc375-body"
    warm(s)
    deny3, t3 = hook("grep -rn -A8 helper pkg/", session=s)
    res["dup_readbody_teaches"] = only_teach(t3, "devkb symbol helper --source")
    res["dup_not_denied"] = not (deny1 or deny2 or deny3)

    s = "acc375-off"
    warm(s)
    _, t4 = hook("grep -n helper pkg/use.py", session=s, DEVKB_GUARDRAIL_TEACH="0")
    res["teach_off"] = "devkb uses" not in t4 and not re.search(r"pkg/\w+\.py:\d+", t4)

    _, t5 = hook("sed -n 1,3p pkg/long.py", session="acc375-span")
    res["span_hint_teaches"] = "long_one" in t5 and "devkb symbol long_one --source" in t5

    s = "acc375-default"
    warm(s)
    _, t7 = hook("grep -n helper pkg/use.py", session=s, DEVKB_GUARDRAIL_TEACH_ALL="")
    res["off_by_default"] = t7 == ""

    _, t6 = hook('grep -rn "def nosuchname_r" pkg/', session="acc375-remind")
    res["reminder_no_mcp_no_log"] = (t6.startswith("devkb guardrail:") and "devkb " in t6.replace("devkb guardrail:", "")
                                     and "mcp__devkb" not in t6 and "dogfood log" not in t6)
res["pass"] = all(res.values())
print(json.dumps(res))
