"""#274: a search with an ambiguous or unknown name is answered alongside instead of passing through. Black box: the checkout's
own PreToolUse hook (scripts/devkb_guardrail.py) on a fixture repository with a built graph.
- callsites_ambiguous_answered_alongside: `grep -rn pending pkg/` (`pending` defined in two files) is not a pass-through; it is
  answered alongside (not a deny) and what it adds names the call sites grep also prints;
- callsites_ambiguous_not_replaced: that search is never replaced (denied);
- locate_several_names_alongside: `grep -rn "def pending\\|def helper" pkg/` is answered alongside with the definition lines of
  every name, both `pending` files and `helper`;
- locate_several_names_not_replaced: and is not denied while a name is ambiguous;
- unknown_name_does_not_block: `grep -rn "def helper\\|def nosuchname" pkg/` still gets helper's definition, alongside or
  as a replacement that carries it;
- unknown_name_adds_nothing: the answer does not invent a definition for the unknown name;
- replacement_needs_every_name: a replacement (deny), if any, of a search with an ambiguous name carries every line grep prints."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
files = {
    "pkg/__init__.py": "",
    "pkg/a.py": "def pending(x):\n    return x + 1\n",
    "pkg/b.py": "def pending(y):\n    return y * 2\n",
    "pkg/lib.py": "def helper(x):\n    total = x + 1\n    return total\n",
    "pkg/use.py": "from pkg.a import pending\nfrom pkg.lib import helper\n\n\ndef go():\n    r = pending(3)\n    return helper(r)\n",
    "pkg/use2.py": "from pkg.b import pending\n\n\ndef go2():\n    return pending(4)\n",
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
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL="1")
    for k in ("DEVKB_GUARDRAIL_TEACH", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, timeout=600)
    n = [0]

    def hook(cmd):
        """(kind, text): 'deny', 'along' (additional context) or 'none' (nothing, or a guardrail reminder)."""
        n[0] += 1
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(A),
              "session_id": f"acc274-{n[0]}", "tool_use_id": f"t274-{n[0]}"}
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
        if os.environ.get("DEBUG274"):
            print(f"[{kind}] {cmd}\n{text}\n", file=sys.stderr)
        return kind, text

    def grep(cmd):
        return subprocess.run(cmd, shell=True, cwd=A, capture_output=True, text=True).stdout

    def has(text, *needles):
        return all(s in text for s in needles)

    # call sites of a name with two definitions
    kind, text = hook("grep -rn pending pkg/")
    res["callsites_ambiguous_answered_alongside"] = kind == "along" and has(text, "pending(3)", "pending(4)")
    res["callsites_ambiguous_not_replaced"] = kind != "deny"

    # definition search for several names, one ambiguous
    cmd = 'grep -rn "def pending\\|def helper" pkg/'
    kind, text = hook(cmd)
    res["locate_several_names_alongside"] = kind == "along" and has(text, "pkg/a.py", "pkg/b.py", "def helper", "def pending(x)", "def pending(y)")
    res["locate_several_names_not_replaced"] = kind != "deny"
    real = [m.group(1).strip() for ln in grep(cmd).splitlines() if (m := re.match(r"^[^:]+:\d+:(.*)$", ln))]
    res["replacement_needs_every_name"] = kind != "deny" or (bool(real) and all(c in text for c in real))

    # a name with no definition does not block the others and adds nothing
    kind, text = hook('grep -rn "def helper\\|def nosuchname" pkg/')
    res["unknown_name_does_not_block"] = kind in ("along", "deny") and "def helper" in text
    res["unknown_name_adds_nothing"] = not re.search(r"pkg/\w+\.py:\d+[:-].*nosuchname", text)
res["pass"] = all(res.values())
print(json.dumps(res))
