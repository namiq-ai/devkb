"""#329: the guardrail's one reminder per session is not spent on a literal, anchored grep (which the reminder's own text says is
grep's job), and still reaches the first search that asks where a defined name is. Black box: the checkout's own hook script run on a
fixture repository, as accept/137 does."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
with tempfile.TemporaryDirectory() as td:
    A, home = Path(td) / "a", Path(td) / "home"
    for d in (A, home / ".claude" / "hooks"):
        d.mkdir(parents=True)
    (A / "mod.py").write_text("REPO = 1\nB = 2\n\n\ndef run_suite(w):\n    return w\n\n\ndef caller():\n    return run_suite(1)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=A, check=True, capture_output=True)
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore", DEVKB_GUARDRAIL_TEACH="0",
               PATH=f"{W / '.venv' / 'bin'}:{os.environ['PATH']}")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else sys.executable
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(A)], cwd=A, env=env, capture_output=True, timeout=600)

    def hook(session, command):
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(A), "session_id": session}
        p = subprocess.run([py, str(W / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), cwd=A, env=env, capture_output=True, text=True, timeout=120)
        return p.stdout

    out = hook("s1", 'grep -n "^REPO\\|^B =" mod.py')
    res["literal_grep_gets_no_reminder"] = "devkb guardrail" not in out
    out2 = hook("s1", "grep -rn run_suite .")
    res["the_next_name_search_still_gets_the_reminder_or_an_answer"] = bool(out2.strip())
    out3 = hook("s2", "grep -rn run_suite .")
    res["a_name_search_first_in_a_session_gets_it_too"] = bool(out3.strip())
res["pass"] = all(res.values())
print(json.dumps(res))
