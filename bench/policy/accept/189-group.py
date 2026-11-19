"""#189 with #190 on a finished checkout: guardrail-stats --project counts only that repository; a `uses` reply with
text matches is fallback-text, not complete."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
out = {}
code = ("import json,sys; from devkb import outcomes as o; "
        "print(json.dumps([o.outcome_of_reply({'mode':'word','n_hits':2,'files':[]})[0], o.outcome_of_reply({'matches':[{'k':'a::f'}],'n':1})[0]]))")
p = subprocess.run([PY, "-P", "-c", code], cwd=W, env=ENV, capture_output=True, text=True, timeout=60)
got = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else []
out["uses_fallback_text"] = got == ["fallback-text", "complete"]
with tempfile.TemporaryDirectory() as td:
    log = Path(td) / "g.log"
    a, b = Path(td) / "a", Path(td) / "b"
    a.mkdir(); b.mkdir()
    log.write_text("\n".join(json.dumps({"session": "s", "repo": str(r), "action": act}) for r, act in ((a, "substitute"), (b, "alongside"), (b, "alongside"))) + "\n")
    run = lambda *x: subprocess.run([PY, "-P", "-m", "devkb.cli", "guardrail-stats", "--log", str(log), *x], cwd=W, env=ENV,
                                    capture_output=True, text=True, timeout=60).stdout
    out["project_filter"] = run("--project", str(a)).startswith("1 guardrail decision") and run().startswith("3 guardrail decision")
out["pass"] = all(out.values())
print(json.dumps(out))
