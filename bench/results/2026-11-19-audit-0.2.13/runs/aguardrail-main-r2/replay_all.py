import json, subprocess, os, tempfile, collections
R = os.getcwd()
home = tempfile.mkdtemp()
out = []
for i, l in enumerate(open('audit/searches.jsonl')):
    d = json.loads(l)
    if d['tool'] not in ('Bash', 'Grep'):
        continue
    ev = {"tool_name": d['tool'], "tool_input": d['input'], "cwd": R, "session_id": "s%d" % i, "tool_use_id": "t%d" % i}
    env = dict(os.environ, HOME=home)
    p = subprocess.run([R + '/.venv/bin/python', 'scripts/devkb_guardrail.py'], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    o = p.stdout.strip()
    if not o:
        continue
    j = json.loads(o)
    h = j.get('hookSpecificOutput', {})
    out.append({"i": i, "in": d['input'], "dec": h.get('permissionDecision'),
                "ctx": h.get('additionalContext') or h.get('permissionDecisionReason')})
json.dump(out, open('audit/replay_out.json', 'w'))
print(len(out))
print(collections.Counter((x['dec'], (x['ctx'] or '')[:30]) for x in out).most_common(15))
