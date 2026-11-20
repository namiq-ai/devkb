"""#281: an answer to a search cut by `| head -N` / `| tail -N` or Grep `head_limit` is never larger than the cut output: it is capped at
N lines or left out (the search runs untouched). Black box: the checkout's own hook script on a fixture repository."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
DATA = re.compile(r"^\S+\.py:\d+")  # a result line: path:line:...


def main(td):
    A, home = Path(td) / "a", Path(td) / "home"
    (A / "pkg").mkdir(parents=True)
    home.mkdir()
    (A / "pkg" / "__init__.py").write_text("")
    (A / "pkg" / "a.py").write_text("def helper(x):\n    return x * 2\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(4)))
    (A / "pkg" / "b.py").write_text("def handler(r):\n    return r\n\n\n" + "".join(f"def h{i}():\n    return handler({i})\n\n\n" for i in range(4)))
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL_TEACH="0",
               PATH=f"{W / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else sys.executable
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, timeout=600)

    def hook(session, tool, inp):
        ev = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp, "cwd": str(A), "session_id": session,
              "tool_use_id": session}
        p = subprocess.run([py, str(W / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), cwd=A, env=env, capture_output=True,
                           text=True, timeout=120)
        if not p.stdout.strip():
            return "none", ""
        d = json.loads(p.stdout)["hookSpecificOutput"]
        return d.get("permissionDecision", "ctx"), d.get("permissionDecisionReason") or d.get("additionalContext") or ""

    def n_data(text):
        return sum(1 for l in text.splitlines() if DATA.match(l))

    def capped(key, session, tool, inp, n):
        dec, text = hook(session, tool, inp)
        # an untouched search (no decision) or an answer of at most n result lines are both fine
        res[key] = dec == "none" or n_data(text) <= n

    capped("head_1_caps_answer", "s1", "Bash", {"command": "grep -rn helper pkg | head -1"}, 1)
    capped("head_2_caps_answer", "s2", "Bash", {"command": "grep -rn handler pkg | head -2"}, 2)
    capped("tail_2_caps_answer", "s3", "Bash", {"command": "grep -rn helper pkg | tail -2"}, 2)
    capped("head_dash_n_form_caps_answer", "s4", "Bash", {"command": "grep -rn helper pkg | head -n 1"}, 1)
    capped("grep_tool_head_limit_caps_answer", "s5", "Grep",
           {"pattern": "handler", "path": "pkg", "output_mode": "content", "head_limit": 2}, 2)
    # guard: the hook still returns well-formed output for a limit larger than the output
    dec, _ = hook("s6", "Bash", {"command": "grep -rn helper pkg | head -50"})
    res["large_head_still_well_formed"] = dec in ("none", "deny", "ctx")
    # guard: an uncut name search is still answered or reminded
    _, text = hook("s7", "Bash", {"command": "grep -rn helper pkg"})
    res["uncut_search_still_handled"] = bool(text.strip())


with tempfile.TemporaryDirectory() as td:
    main(td)
res["pass"] = all(res.values())
print(json.dumps(res))
