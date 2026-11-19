import json, os, subprocess, sys, uuid
from pathlib import Path
root = Path(__file__).resolve().parents[1]
repo = root / "audit" / "_rp"
home = root / "audit" / "_home"
home.mkdir(exist_ok=True)
out = []
for i, line in enumerate(open(root / "audit" / "searches.jsonl")):
    s = json.loads(line)
    if s["tool"] not in ("Bash", "Grep"):
        continue
    ev = {"tool_name": s["tool"], "tool_input": s["input"], "cwd": str(repo), "session_id": f"s{i}", "tool_use_id": f"t{i}-{uuid.uuid4().hex[:6]}"}
    env = dict(os.environ, HOME=str(home), DEVKB_GUARDRAIL="1", DEVKB_GUARDRAIL_TEACH="1", PYTHONPATH=str(repo))
    p = subprocess.run([sys.executable, "-P", str(repo / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True, env=env, cwd=repo)
    try:
        o = json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError:
        o = {"raw": p.stdout}
    out.append({"i": i, "tool": s["tool"], "input": s["input"], "out": o, "err": p.stderr[-300:]})
json.dump(out, open(root / "audit" / "replay_out.json", "w"))
log = home / ".claude" / "hooks" / "devkb-guardrail.log"
print(len(out), "replayed;", sum(1 for o in out if o["out"] and "remind" not in json.dumps(o["out"])[:400]), "with output")
