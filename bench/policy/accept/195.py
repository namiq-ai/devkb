"""#195 on a finished checkout: extracting module constants is linear, and each constant is still one symbol.

With the checkout's own devkb, one file of N module constants:
- `linear`: extract time of 18,000 constants over 6,000 is below 5 (linear gives about 3, the 0.2.12 scan about 9);
- `fast_18000`: 18,000 constants extract in under 4 s (0.2.12: about 9 s);
- `deduped`: a constant assigned twice (`X = 1` then `X = 2`) and a dataclass field are still one symbol each, and
  the last constant of the big file is found by `symbol`.
"""
import json, subprocess, sys, tempfile, time
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = {"PYTHONPATH": str(W), "PATH": "/usr/bin:/bin"}


def repo(root: Path, n: int, extra: str = "") -> Path:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "table.py").write_text("\n".join(f"NAME_{i} = {i}" for i in range(n)) + "\n" + extra)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    return root


def secs(root: Path) -> float:
    code = ("import time; from pathlib import Path; from devkb import build_symbols as b; "
            f"t=time.perf_counter(); b.extract(Path({str(root)!r})); print(time.perf_counter()-t)")
    p = subprocess.run([PY, "-P", "-c", code], cwd=W, env=ENV, capture_output=True, text=True, timeout=900)
    return float(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else float("inf")


out = {}
with tempfile.TemporaryDirectory(dir=str(W.parent)) as td:
    a, b = repo(Path(td) / "a", 6000), repo(Path(td) / "b", 18000)
    ta, tb = secs(a), secs(b)
    out["t6000"], out["t18000"] = round(ta, 2), round(tb, 2)
    out["linear"] = tb / ta < 5 if ta > 0 else False
    out["fast_18000"] = tb < 4
    c = repo(Path(td) / "c", 50, "X = 1\nX = 2\n\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass P:\n    port: int = 0\n    port: int = 1\n")
    code = ("import json; from pathlib import Path; from devkb import build_symbols as b; "
            f"syms=b._parse_python_file(Path({str(c)!r}) / 'pkg' / 'table.py', [])[0]; "
            "print(json.dumps(['pkg/table.py::' + s['qualified_name'] for s in syms]))")
    p = subprocess.run([PY, "-P", "-c", code], cwd=W, env=ENV, capture_output=True, text=True, timeout=300)
    keys = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else []
    out["x_once"] = keys.count("pkg/table.py::X") == 1
    out["field_once"] = keys.count("pkg/table.py::P.port") == 1
    out["last_found"] = "pkg/table.py::NAME_49" in keys
    out["deduped"] = out["x_once"] and out["field_once"] and out["last_found"]
out["pass"] = all(out[k] for k in ("linear", "fast_18000", "deduped"))
print(json.dumps(out))
