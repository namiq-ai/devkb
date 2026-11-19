import sys, os, json, subprocess, tempfile
sys.path.insert(0, "audit/repro")
import fx
root = fx.make_repo({"lib/x.rb": "def foo_bar\n  1\nend\n\ndef other\n  foo_bar\nend\n", "pkg/__init__.py": ""})
home = tempfile.mkdtemp()
env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
env["HOME"] = home
POST = str(fx.ROOT / "scripts/devkb_guardrail_post.py")
for i, (cmd, out) in enumerate([
    ('grep -n "def foo_bar" lib/x.rb', "1:def foo_bar"),
    ('grep -n "def foo_bar" -A3 lib/x.rb', "1:def foo_bar\n2-  1\n3-end\n4-\n"),
    ('grep -rn foo_bar lib', "lib/x.rb:1:def foo_bar\nlib/x.rb:6:  foo_bar"),
    ('grep -n foo_bar lib/x.rb', "1:def foo_bar\n6:  foo_bar"),
    ('cd lib && grep -n foo_bar x.rb', "1:def foo_bar\n6:  foo_bar"),
    ('grep -c foo_bar lib/x.rb', "2"),
    ('grep -rn foo_bar lib | head -1', "lib/x.rb:1:def foo_bar"),
]):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(root), "session_id": f"p{i}", "tool_use_id": f"u{i}"}
    pre = subprocess.run([str(fx.ROOT / ".venv/bin/python"), str(fx.PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env)
    ev2 = dict(ev, tool_response={"stdout": out})
    subprocess.run([str(fx.ROOT / ".venv/bin/python"), POST], input=json.dumps(ev2), capture_output=True, text=True, env=env)
    print(cmd, "->", "pre-out" if pre.stdout.strip() else "silent")
p = root / ".devkb/graph-misses.jsonl"
for l in p.read_text().splitlines() if p.exists() else []:
    d = json.loads(l)
    print(d["pattern"], d["verdict"], d["grep"]["matches"], d["grep"]["count"])
