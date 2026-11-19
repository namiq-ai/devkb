"""#194 on a finished checkout: build time is linear in typed-receiver calls, and those calls still resolve.

Synthetic repositories (as the audit's r05): N files, each with 20 functions doing 2 typed calls (s: Store) and
3 untyped ones. With the checkout's own devkb:
- `linear`: extract time of 450 files over 150 files is below 5 (linear gives about 3, the 0.2.12 quadratic about 9);
- `fast_450`: 450 files extract in under 30 s (0.2.12: about 45 s; 0.2.11: about 7 s on this machine);
- `resolved`: on 30 files, `pack refactor Store.put` lists all 30 files as direct callers (the typed calls resolve).
"""
import json, re, subprocess, sys, tempfile, time
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")


def gen(root: Path, n: int):
    files = {"pkg/__init__.py": "", "pkg/core.py": "class Store:\n    def put(self, x):\n        return x\n\n    def get(self, x):\n        return x\n"}
    for i in range(n):
        body = ["from pkg.core import Store", "", ""]
        for j in range(20):
            body += [f"def f{j}(s: Store, obj):", "    s.put(1)", "    s.get(2)", "    obj.get(3)", "    obj.put(4)", "    obj.x.get(5)", ""]
        files[f"pkg/m{i}.py"] = "\n".join(body) + "\n"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)


def extract_secs(root: Path) -> float:
    code = ("import time,sys; sys.setrecursionlimit(10000); from pathlib import Path; from devkb import build_symbols as b; "
            f"t=time.perf_counter(); b.extract(Path({str(root)!r})); print(time.perf_counter()-t)")
    p = subprocess.run([PY, "-P", "-c", code], cwd=W, env={"PYTHONPATH": str(W), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=900)
    return float(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else float("inf")


out = {}
with tempfile.TemporaryDirectory(dir=str(W.parent)) as td:
    a, b, c = Path(td) / "a150", Path(td) / "b450", Path(td) / "c30"
    gen(a, 150); gen(b, 450); gen(c, 30)
    t150, t450 = extract_secs(a), extract_secs(b)
    out["t150"], out["t450"] = round(t150, 2), round(t450, 2)
    out["linear"] = t450 / t150 < 5 if t150 > 0 else False
    out["fast_450"] = t450 < 30
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(c)], cwd=W, env={"PYTHONPATH": str(W), "PATH": "/usr/bin:/bin"}, capture_output=True, timeout=900)
    pack = subprocess.run([PY, "-P", "-m", "devkb.cli", "pack", "refactor", "Store.put", "--project", str(c)], cwd=W,
                          env={"PYTHONPATH": str(W), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=300).stdout
    m = re.search(r"Files with a direct caller \((\d+)", pack)
    out["callers"] = int(m.group(1)) if m else None
    out["resolved"] = out["callers"] == 30
out["pass"] = all(out[k] for k in ("linear", "fast_450", "resolved"))
print(json.dumps(out))
