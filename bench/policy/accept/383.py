"""#383: `devkb build --allow-foreign-checkout` builds the graph of another devkb checkout (both stages); without the
flag the refusal stays.
Black box: the checkout's own CLI on a fresh clone of the checkout; prints one JSON line."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
res = {}
with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, HOME=str(Path(td)), PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG", "DEVKB_DIR"):
        env.pop(k, None)

    def clone(name):
        d = Path(td) / name
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", f"file://{W}", str(d)], check=True,
                       capture_output=True)
        return d

    def build(d, *flags):
        return subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", ".", *flags], cwd=d, env=env,
                              capture_output=True, text=True, timeout=900)

    a = clone("with_flag")
    p = build(a, "--allow-foreign-checkout")
    out = p.stdout + p.stderr
    res["flag_accepted"] = "unrecognized arguments" not in out and p.returncode == 0
    res["both_stages_built"] = (a / ".devkb" / "nodes.jsonl").exists() and (a / ".devkb" / "edges.jsonl").exists() \
        and (a / ".devkb" / "symbols-nodes.jsonl").exists()
    b = clone("without_flag")
    q = build(b)
    res["refusal_kept_without_flag"] = q.returncode != 0 and "allow-foreign-checkout" in (q.stdout + q.stderr) \
        and not (b / ".devkb" / "nodes.jsonl").exists()
    res["refused_build_writes_no_symbols"] = not list((b / ".devkb").glob("symbols-*"))
print(json.dumps({"results": res, "pass": all(res.values())}))
