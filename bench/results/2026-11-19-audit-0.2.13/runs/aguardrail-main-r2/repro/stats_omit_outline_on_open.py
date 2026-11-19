import sys, os, json, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import fx

src = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(50))     # 200 lines: above OUTLINE_MIN_LINES
root = fx.make_repo({"pkg/__init__.py": "", "pkg/big.py": src})
home = tempfile.mkdtemp()
env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
env.update(HOME=home, DEVKB_GUARDRAIL_OUTLINE="1")
ev = {"tool_name": "Read", "tool_input": {"file_path": str(root / "pkg/big.py")}, "cwd": str(root), "session_id": "s1",
      "tool_use_id": "t1"}
out = subprocess.run([str(fx.ROOT / ".venv/bin/python"), str(fx.PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
log = os.path.join(home, ".claude/hooks/devkb-guardrail.log")
logged = open(log).read() if os.path.exists(log) else ""
print("hook answered with an outline:", bool(out.strip()), "| log:", logged.strip()[:200])
stats = subprocess.run([str(fx.ROOT / ".venv/bin/python"), "-m", "devkb.cli", "guardrail-stats", "--log", log], capture_output=True,
                       text=True, env=dict(os.environ, PYTHONPATH=str(fx.ROOT), PYTHONWARNINGS="ignore")).stdout
print(stats)
if "outline-on-open" in logged and "outline-on-open" not in stats:
    print("DEFECT: guardrail-stats leaves out the outline-on-open decisions it was given")
    sys.exit(1)
print("ok")
