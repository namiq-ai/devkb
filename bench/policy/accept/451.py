"""#451: a Zephyr benchmark agent is started sandboxed with its own temp folder and none of the launching session's variables, and a batch refuses to
start without a passing isolation self-test. Black box on what reaches the agent: the checkout's harness runs a stand-in `claude` that records its
arguments and environment. Whether the sandbox then holds on a host is `zbench.py isolation`, which this does not run. Prints one JSON line."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
DRIVER = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import zbench
for n in ("a", "b"):
    d = Path(sys.argv[2]) / "out" / n
    d.mkdir(parents=True)
    zbench.OUT = d.parent
    zbench.run_agent(Path(sys.argv[2]), "none", "prompt", d)
import batch
batch.zbench.OUT = Path(sys.argv[2]) / "empty"
try:
    print("PREFLIGHT " + " | ".join(batch.preflight()))
except Exception as e:
    print(f"PREFLIGHT-ERROR {e!r}")
'''
STANDIN = '''#!/usr/bin/env python3
import json, os, sys
if "--version" in sys.argv:
    print("0.0.0"); sys.exit(0)
with open(os.environ["RECORD"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ), "tmp_exists": os.path.isdir(os.environ.get("TMPDIR", "/nonexistent"))}) + "\\n")
'''
res, detail = {}, {}
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    (t / "bin").mkdir()
    (t / "bin" / "claude").write_text(STANDIN)
    (t / "bin" / "claude").chmod(0o755)
    (t / "run" / "shims").mkdir(parents=True)
    (t / "run" / "shims" / "claude").symlink_to(t / "bin" / "claude")
    cbm = t / "run" / "cbm" / "bin" / "codebase-memory-mcp"      # the batch preflight asks its version
    cbm.parent.mkdir(parents=True)
    cbm.write_text("#!/bin/sh\necho codebase-memory-mcp 0.0.0\n")
    cbm.chmod(0o755)
    env = dict(os.environ, ZBENCH_RUN=str(t / "run"), ZBENCH_SCRATCH=str(t / "scratch"), RECORD=str(t / "calls.jsonl"), CLAUDE_EFFORT="max",
               CLAUDE_CODE_SESSION_ID="launcher", PATH=f"{t / 'bin'}:{os.environ['PATH']}", PYTHONWARNINGS="ignore")
    p = subprocess.run([py, "-c", DRIVER, str(W / "bench" / "zephyr"), str(t)], env=env, capture_output=True, text=True, timeout=300)
    calls = [json.loads(x) for x in (t / "calls.jsonl").read_text().splitlines()] if (t / "calls.jsonl").exists() else []
    res["two agent runs started"] = len(calls) == 2
    if len(calls) == 2:
        a, b = calls
        s = json.loads(a["argv"][a["argv"].index("--settings") + 1]) if "--settings" in a["argv"] else {}
        box = s.get("sandbox", {})
        fs = box.get("filesystem", {})
        res["sandbox on, refuses to start without it"] = box.get("enabled") is True and box.get("failIfUnavailable") is True
        res["no command can opt out"] = box.get("allowUnsandboxedCommands") is False and not box.get("excludedCommands")
        res["file tools held to the working directories"] = s.get("permissions", {}).get("blockWritesOutsideWorkingDirectories") is True
        res["only the run's own folder is opened"] = len(fs.get("allowWrite", [])) == 1 and fs["allowWrite"][0].startswith(str(t / "scratch"))
        run = str(t / "run")
        res["clone git, hidden checks and tasks not writable"] = all(f"{run}/{x}" in fs.get("denyWrite", []) for x in ("zephyr-src/.git", "hidden", "tasks"))
        res["hidden checks and tasks not readable"] = all(f"{run}/{x}" in fs.get("denyRead", []) for x in ("hidden", "tasks"))
        res["own temp folder, present at start"] = a["tmp_exists"] and a["env"]["TMPDIR"].startswith(str(t / "scratch"))
        res["two runs do not share temp"] = a["env"]["TMPDIR"] != b["env"]["TMPDIR"]
        res["launching session's variables dropped"] = "CLAUDE_EFFORT" not in a["env"] and "CLAUDE_CODE_SESSION_ID" not in a["env"]
    res["batch refuses without a self-test"] = "isolation self-test" in p.stdout
    detail = {"rc": p.returncode, "err": p.stderr[-400:]}
print(json.dumps({"pass": bool(res) and all(res.values()), "checks": res, "detail": detail}))
