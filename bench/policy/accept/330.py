"""#330: a benchmark run's stream records what the hook said to the agent. Black box: the claude command policybench._run_one builds asks for hook events, and storybench.transcript reports the hook outputs of a stream that has them."""
import importlib, json, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(W / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = pb.sb
res = {}
td = tempfile.mkdtemp()
pb.B = Path(td)
def fake_from_template(t, w):
    Path(w).mkdir(parents=True, exist_ok=True); (Path(w) / ".bench-arm.json").write_text("{}")
pb.template_for = lambda a, issue=None: Path(td) / "t"; pb.from_template = fake_from_template
pb.toolenv.build = lambda ref: {"bin": str(Path(td) / "bin" / "devkb"), "commit": "x", "hook_sha": "x"}
pb.score_run = lambda *a, **k: None
real_run, real_sh = subprocess.run, sb.sh
sb.sh = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else real_sh(cmd, **kw)
got = {}
def fake_run(cmd, *a, **k):
    if cmd and cmd[0] == "claude":
        got["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)
    return real_run(cmd, *a, **k)
pb.subprocess.run = fake_run
try:
    pb._run_one("9999", "main", 1)
finally:
    pb.subprocess.run, sb.sh = real_run, real_sh
res["run_asks_for_hook_events"] = "--include-hook-events" in got.get("cmd", [])

def hook(i, text):
    return {"type": "system", "subtype": "hook_response", "hook_id": f"h{i}", "hook_name": "PreToolUse:Bash", "hook_event": "PreToolUse",
            "output": json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}), "exit_code": 0, "outcome": "success"}
def asst(i):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": {"output_tokens": 1}, "content": []}}
base_ev = [{"type": "system", "subtype": "init", "session_id": "s"}, asst(1), asst(2)]
with_hooks = [base_ev[0], hook(1, "STUB-REMINDER-ONE"), asst(1), hook(2, "second answer"), asst(2)]
sb.guardrail_actions = lambda s, log=None: (0, {})
def transcript(events):
    p = Path(td) / "s.jsonl"; p.write_text("".join(json.dumps(x) + "\n" for x in events)); return sb.transcript(p)
base, t = transcript(base_ev), transcript(with_hooks)
res["transcript_carries_the_first_hook_output"] = "STUB-REMINDER-ONE" in json.dumps(t)
new = [k for k in t if k not in base or t[k] != base[k]]
res["transcript_counts_two_hook_outputs"] = any(t[k] == 2 or (isinstance(t[k], (list, dict)) and len(t[k]) == 2) for k in new)
res["pass"] = all(res.values())
print(json.dumps(res))
