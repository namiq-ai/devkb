"""#389: `pack file` lists a file that runs a module by name (`runpy.run_module("pkg.mod")`, a `-m` command) among the module's dependents, or says its
dependents list may be incomplete and names those files. Black box: the checkout's own CLI on a fixture repository; prints one JSON line."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
FILES = {
    "pkg/__init__.py": "",
    "pkg/mod.py": "def main():\n    return 1\n\n\nif __name__ == '__main__':\n    main()\n",
    "pkg/model.py": "def other():\n    return 2\n",
    "tools/run_a.py": "import runpy\n\n\ndef go():\n    return runpy.run_module('pkg.mod', run_name='__main__')\n",
    "tools/run_b.py": "import subprocess\nimport sys\n\n\ndef go():\n    return subprocess.run([sys.executable, '-m', 'pkg.mod', '--x'])\n",
    "tools/unrelated.py": "def go():\n    return 'pkg.model is another module'\n",
}
res = {}
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@e.x", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=repo, check=True, capture_output=True)
    env = dict(os.environ, HOME=td, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG", "DEVKB_DIR"):
        env.pop(k, None)
    b = subprocess.run([py, "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, env=env, capture_output=True, text=True, timeout=600)
    res["builds"] = b.returncode == 0
    p = subprocess.run([py, "-P", "-m", "devkb.cli", "pack", "--project", str(repo), "file", "pkg/mod.py"], cwd=repo, env=env, capture_output=True, text=True, timeout=300)
    text = p.stdout
    m = re.search(r"## Files that depend on it[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
    dep = m.group(1) if m else ""
    incomplete = bool(re.search(r"incomplete|may be missing|not all|by name", text, re.I))
    for f in ("tools/run_a.py", "tools/run_b.py"):
        res[f"{f}_listed_or_named_as_incomplete"] = f in dep or (incomplete and f in text)
    res["an_unrelated_string_is_not_a_dependent"] = "tools/unrelated.py" not in dep and "pkg/model.py" not in dep
print(json.dumps({"results": res, "pass": all(res.values())}))
