import sys, os, json, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import fx

root = fx.make_repo({"lib/x.rb": "def foo_bar\n  1\nend\n\ndef other\n  foo_bar\nend\n", "pkg/__init__.py": ""})
home = tempfile.mkdtemp()
env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
env["HOME"] = home
py = str(fx.ROOT / ".venv/bin/python")
POST = str(fx.ROOT / "scripts/devkb_guardrail_post.py")
log = root / ".devkb/graph-misses.jsonl"
cases = ['grep -n foo_bar lib/x.rb | head -5', 'grep -n foo_bar lib/x.rb 2>&1', 'cd lib && grep -n foo_bar x.rb',
         'grep -n foo_bar lib/x.rb 2>/dev/null']
bad = []
for i, cmd in enumerate(cases):
    before = len(log.read_text().splitlines()) if log.exists() else 0
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(root), "session_id": f"m{i}", "tool_use_id": f"u{i}"}
    subprocess.run([py, str(fx.PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env)
    subprocess.run([py, POST], input=json.dumps(dict(ev, tool_response={"stdout": "1:def foo_bar\n6:  foo_bar\n"})),
                   capture_output=True, text=True, env=env)
    after = len(log.read_text().splitlines()) if log.exists() else 0
    print(f"{cmd!r}: grep found code in lib/x.rb, graph-miss lines added: {after - before}")
    if after == before:
        bad.append(cmd)
if bad:
    print("DEFECT: a single-file `grep -n` is not logged as a graph miss when it has a pipe, a redirection or a leading cd:", bad)
    sys.exit(1)
print("ok")
