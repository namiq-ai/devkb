"""#400: a call on a name bound by unpacking a helper's tuple of constructed objects is attributed, helper in the same repository (same or another file). Black box: python bench/policy/accept/400.py CHECKOUT."""
import json, subprocess, sys, tempfile
from pathlib import Path
W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
R = Path(tempfile.mkdtemp())
(R / "pkg").mkdir()
(R / "pkg" / "m.py").write_text("class Api:\n    def go(self):\n        return 1\n\n\nclass Packer:\n    def run(self):\n        return 2\n")
(R / "pkg" / "h.py").write_text("from pkg.m import Api, Packer\n\n\ndef make():\n    a = Api()\n    return a, Packer()\n")
(R / "pkg" / "same.py").write_text("from pkg.m import Api, Packer\n\n\ndef make2():\n    a = Api()\n    return a, Packer()\n\n\ndef use2():\n    api, packer = make2()\n    api.go()\n")
(R / "pkg" / "t.py").write_text("import pkg.h as H\n\n\ndef use():\n    api, packer = H.make()\n    api.go()\n    packer.run()\n")
for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
    subprocess.run(["git", *c], cwd=R, capture_output=True)
subprocess.run([PY, "-m", "devkb.cli", "build", "--project", str(R)], cwd=W, env={**__import__("os").environ, "PYTHONPATH": str(W)}, capture_output=True, timeout=300)
refs = {json.loads(l)["properties"].get("evidence_ref", "") for l in (R / ".devkb" / "edges.jsonl").read_text().splitlines() if json.loads(l).get("verb") == "CALLS"}
ok = {"same_file_helper": any(r.startswith("pkg/same.py::use2 calls go") for r in refs),
      "other_file_helper": any(r.startswith("pkg/t.py::use calls go") for r in refs) and any(r.startswith("pkg/t.py::use calls run") for r in refs)}
print(json.dumps({"pass": all(ok.values()), **ok}))
