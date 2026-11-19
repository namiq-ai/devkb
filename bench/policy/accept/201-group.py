"""#201 with #202 on a finished checkout: a prefix match does not hide a name's string-key uses; `"k" in d` is a read,
`d["k"] += 1` a read and a write, `d.update(k=...)` a write, and os.environ.get("k") is not a record key."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
APP = ('import os\n\n\ndef write(rec):\n    rec["status"] = "ok"\n    rec["count"] += 1\n    rec.update(owner="me")\n'
       '    return dict(status="new")\n\n\ndef read(rec):\n    if "status" in rec:\n        return rec["status"]\n'
       '    return rec.get("status")\n\n\ndef env():\n    return os.environ.get("status")\n')
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    (r / "app.py").write_text(APP)
    (r / "other.py").write_text("def status_of(job):\n    return job\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=ENV, capture_output=True, timeout=300)
    sym = lambda n: subprocess.run([PY, "-P", "-m", "devkb.cli", "symbol", n, "--project", str(r)], cwd=W, env=ENV, capture_output=True,
                                   text=True, timeout=120).stdout
    s, c, o = sym("status"), sym("count"), sym("owner")
    reads = re.search(r"read\s+reads L([\d,]+)", s)
    out = {"prefix_keeps_keys": "status_of" in s and "string key" in s,
           "membership_read": bool(reads) and "12" in reads.group(1).split(","),
           "environ_not_a_key": bool(reads) and "18" not in reads.group(1).split(","),
           "augmented_read": "reads L6" in c, "keyword_write": "string key" in o and "writes L7" in o}
out["pass"] = all(out.values())
print(json.dumps(out))
