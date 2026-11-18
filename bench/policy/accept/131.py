"""Acceptance of #131 + #133 on a finished checkout, through the hooks the checkout itself registers.

1. substitute: a navigation search for a name the graph resolves Complete (`_first_line`) gets devkb's answer from the
   PreToolUse hook (in any field), and is not a refusal asking to run the search again;
2. pass-through: a search the graph cannot answer (`TELEMETRY_NAME`, a module constant, no symbol) is not refused;
3. miss log: after the PostToolUse hook(s) see the search's output, .devkb/graph-misses.jsonl has a line for it
   carrying the verdict, the name(s), a re-runnable devkb query and what grep found;
4. `devkb misses --project .` exits 0 and prints a draft with a reproduce section;
5. the policy names the log (AGENTS.md mentions graph-misses or `devkb misses`).
"""
import json, os, re, subprocess, sys
from pathlib import Path

w = Path(sys.argv[1]).resolve()
py = str(w / ".venv" / "bin" / "python")
home = w / ".bench-home"                               # the hooks' own state (markers, logs) away from the real home
home.mkdir(exist_ok=True)
env = dict(os.environ, HOME=str(home), PATH=f"{w / '.venv' / 'bin'}:{os.environ['PATH']}", CLAUDE_PROJECT_DIR=str(w),
           PYTHONPATH=str(w))
env.pop("DEVKB_GUARDRAIL", None)
subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(w)], cwd=w, capture_output=True, timeout=900)
out = {}
settings = json.loads((w / ".claude" / "settings.json").read_text())


def cmds(event):
    return [h["command"] for m in settings.get("hooks", {}).get(event, []) if re.search(m.get("matcher", ".*"), "Bash")
            for h in m["hooks"] if h.get("type") == "command"]


# Claude Code refuses headless writes to .claude/settings.json, even with an explicit permission (verified
# 2026-11-18), so an agent cannot register a new hook. If it wrote the PostToolUse script under the name both
# agents chose and the entry is missing, the scorer registers it as they described, and says so.
POST = w / "scripts" / "devkb_guardrail_post.py"
if not cmds("PostToolUse") and POST.exists():
    settings.setdefault("hooks", {}).setdefault("PostToolUse", []).append(
        {"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": f'python3 "{POST}"'}]})
    out["post_registered_by_scorer"] = True


def run_hooks(event, ev):
    res = []
    for c in cmds(event):
        p = subprocess.run(["bash", "-c", c], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=w, timeout=60)
        res.append(p.stdout.strip())
    return res


def bash_ev(tid, command, session="acc-s1"):
    return {"session_id": session, "tool_use_id": tid, "tool_name": "Bash", "cwd": str(w), "hook_event_name": "PreToolUse",
            "tool_input": {"command": command, "description": "search"}}


out["post_hooks"] = len(cmds("PostToolUse"))
# 1. substitute
pre = run_hooks("PreToolUse", bash_ev("acc-t1", 'grep -rn "def _first_line" devkb'))
blob = "\n".join(pre)
out["substituted"] = bool(re.search(r"build_symbols\.py", blob) and re.search(r"_first_line", blob) and re.search(r"L?\d{2,4}", blob))
out["refusal_to_retry"] = bool(re.search(r"same search again|run exactly the same", blob, re.I))
# 1b. an Incomplete answer is not substituted (fail safe, owner's rule): `logged_pack` is Incomplete in pack change
pre_i = run_hooks("PreToolUse", bash_ev("acc-t0", 'grep -rn "def logged_pack" devkb'))
dec_i = [json.loads(x).get("hookSpecificOutput", {}).get("permissionDecision") for x in pre_i if x.startswith("{")]
out["incomplete_passes"] = "deny" not in dec_i
# 2. pass-through
cmd2 = 'grep -rn "TELEMETRY_NAME" devkb'
pre2 = run_hooks("PreToolUse", bash_ev("acc-t2", cmd2))
dec = [json.loads(x).get("hookSpecificOutput", {}).get("permissionDecision") for x in pre2 if x.startswith("{")]
out["passed_through"] = "deny" not in dec
# 3. miss log, after the search really runs and the PostToolUse hook sees it
g = subprocess.run(["bash", "-c", cmd2], cwd=w, capture_output=True, text=True)
post_ev = dict(bash_ev("acc-t2", cmd2), hook_event_name="PostToolUse",
               tool_response={"stdout": g.stdout, "stderr": g.stderr, "interrupted": False, "isImage": False})
run_hooks("PostToolUse", post_ev)
log = w / ".devkb" / "graph-misses.jsonl"
lines = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
hit = [l for l in lines if "TELEMETRY_NAME" in json.dumps(l)]
out["miss_lines"] = len(hit)
if hit:
    l = hit[-1]; flat = json.dumps(l).lower()
    out["miss_has"] = {f: bool(re.search(f, flat)) for f in ("verdict", "devkb_query|query", "grep|match", "pattern", "session")}
# a resolved name must not be logged as a miss
out["no_miss_for_resolved"] = not any("_first_line" in json.dumps(l) for l in lines)
# 4. devkb misses
m = subprocess.run([py, "-P", "-m", "devkb.cli", "misses", "--project", str(w)], cwd=w, capture_output=True, text=True,
                   env=env, timeout=120)
out["misses_cmd"] = m.returncode == 0 and "TELEMETRY_NAME" in m.stdout and bool(re.search(r"reproduce", m.stdout, re.I))
# 5. policy
out["policy_mentions_log"] = bool(re.search(r"graph-misses|devkb misses", (w / "AGENTS.md").read_text()))
out["pass"] = bool(out["substituted"] and not out["refusal_to_retry"] and out["incomplete_passes"] and out["passed_through"] and out["miss_lines"]
                   and all(out.get("miss_has", {}).values()) and out["no_miss_for_resolved"] and out["misses_cmd"]
                   and out["policy_mentions_log"])
print(json.dumps(out))
