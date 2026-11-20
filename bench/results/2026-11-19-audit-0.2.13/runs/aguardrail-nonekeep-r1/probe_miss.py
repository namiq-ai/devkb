import json, os, subprocess, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "repro"))
from _fx import fixture, hook, grep, PY, ROOT, _env
repo = fixture({"s.lua": "function zzfoo(a)\n  return a\nend\n\nzzfoo(1)\n", "app.py": "import os\n\n\ndef go():\n    return os.environ.get('zzkey')\n"})
home = repo.parent / "home"
for cmd in ['grep -n "zzfoo" s.lua', 'grep -rn "zzfoo" .', 'grep -n "zzkey" app.py']:
    k, t = hook(repo, "Bash", cmd)
    print(cmd, "->", k, t[:100])
    pend = home / ".claude" / "hooks" / ".devkb-guardrail-pending"
    print("  pending:", [p.name for p in pend.iterdir()] if pend.exists() else None)
    # find the key and run the post hook
    for p in (pend.iterdir() if pend.exists() else []):
        out = grep(repo, cmd)
        ev = {"tool_use_id": p.name, "tool_response": {"stdout": out}}
        r = subprocess.run([str(PY), "-P", str(ROOT / "scripts" / "devkb_guardrail_post.py")], input=json.dumps(ev), capture_output=True, text=True, env=_env(home), cwd=repo)
        print("  post rc", r.returncode, r.stderr[-200:])
ml = repo / ".devkb" / "graph-misses.jsonl"
print(ml.read_text() if ml.exists() else "no miss log")
