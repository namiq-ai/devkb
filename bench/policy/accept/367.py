"""#367 (item 1): a replay feeds every Grep and grep/rg Bash call of an archived run's stream through the guardrail,
against a graph of the run's checkout, and prints each decision, its reason, the characters it added and the agent's
next tool call; it is committed with a test.
Black box: `bench/policy/hook_replay.py` of the checkout on a synthetic stream and fixture repository; the invocation
is tried in the usual forms (repository as an option, streams as arguments); prints one JSON line."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
ACTIONS = ("substitute", "read-answer", "alongside", "span-hint", "teach", "remind", "pass-through", "repeat")
res = {}
replay = W / "bench" / "policy" / "hook_replay.py"
res["replay_exists"] = replay.exists()
res["replay_has_a_test"] = any("hook_replay" in p.read_text(errors="replace") for p in (W / "tests").glob("test_*.py"))
out = ""
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    env = dict(os.environ, HOME=str(td / "home"), PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    (td / "home").mkdir()
    repo = td / "repo"
    files = {"pkg/core.py": "def compute_total(rows):\n    return sum(rows)\n\n\ndef other_thing():\n    return compute_total([1])\n",
             "pkg/use.py": "from pkg.core import compute_total\n\n\ndef report():\n    return compute_total([2, 3])\n"}
    for rel, txt in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(txt)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=repo, check=True, capture_output=True)
    subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, env=env, capture_output=True, timeout=600)
    orig = "/home/someone/work/p999-main-r1"          # the run's own checkout, as the stream records it
    tool = lambda i, name, inp: {"type": "assistant", "message": {"id": f"m{i}", "role": "assistant", "content": [
        {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}], "usage": {"input_tokens": 1, "output_tokens": 1}}}
    events = [{"type": "system", "subtype": "init", "cwd": orig, "session_id": "s-367"},
              tool(1, "Grep", {"pattern": "compute_total", "path": orig, "output_mode": "content"}),
              tool(2, "Read", {"file_path": f"{orig}/pkg/core.py"}),
              tool(3, "Bash", {"command": f"grep -rn 'compute_total(' {orig}/pkg"}),
              tool(4, "Bash", {"command": "ls pkg"}),
              tool(5, "Edit", {"file_path": f"{orig}/pkg/core.py", "old_string": "a", "new_string": "b"}),
              {"type": "result", "subtype": "success", "num_turns": 5, "total_cost_usd": 0.01}]
    stream = td / "runs" / "p999-main-r1" / "stream.jsonl"
    stream.parent.mkdir(parents=True)
    stream.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    if replay.exists():
        for args in (["--repo", str(repo), str(stream)], [str(stream), "--repo", str(repo)],
                     ["--repo", str(repo), str(stream.parent)], ["--checkout", str(repo), str(stream)]):
            p = subprocess.run([py, str(replay), *args], cwd=W, env=env, capture_output=True, text=True, timeout=600)
            if p.returncode == 0 and any(a in p.stdout for a in ACTIONS):
                out = p.stdout
                break
SUMMARY = r"(?i)answer[\w -]*rate|answered"
lines = [l for l in out.splitlines() if any(a in l for a in ACTIONS) and not re.search(SUMMARY, l)]
# one decision per search: the Grep call and the grep in Bash, not `ls`, the Read or the Edit (which may still be
# named as a decision's next call)
decisions = [l for l in lines if "compute_total" in l]
res["one_decision_per_search"] = len(lines) == 2 and len(decisions) == 2
res["reason_and_chars_given"] = all(re.search(r"\d", l) for l in decisions) and bool(decisions)
res["next_call_given"] = len(decisions) == 2 and "Read" in decisions[0] and ("ls" in decisions[1] or "Edit" in decisions[1])
res["summary_given"] = bool(re.search(SUMMARY, out))
print(json.dumps({"results": res, "pass": all(res.values())}))
