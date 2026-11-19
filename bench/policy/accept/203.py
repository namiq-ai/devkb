"""#203 on a finished checkout: `symbol` and `outline` give each C++ overload its own range, and `symbol --source` prints
each body on its own.

With the checkout's own devkb on a fixture: `int area(int w)` at L8-10 and `int area(int w, int h)` at L12-14 in src/a.cpp.
- `symbol_ranges`: `symbol area` shows L8-10 and L12-14, not the merged L8-14;
- `source_separate`: `symbol area --source` prints both bodies, and no line between them (L11) as part of a body;
- `outline_ranges`: `outline src/a.cpp` shows L8-10 and L12-14, not L8-14.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
SRC = ("#include <cstdio>\n\nstruct Box { int w; };\n\nint helper(int x) { return x; }\n\n\n"
       "int area(int w) {\n  return w * w;\n}\n\nint area(int w, int h) {\n  return w * h + 7;\n}\n")


def cli(root, *a):
    return subprocess.run([PY, "-P", "-m", "devkb.cli", *a, "--project", str(root)], cwd=W, env=ENV, capture_output=True,
                          text=True, timeout=300).stdout


out = {}
with tempfile.TemporaryDirectory() as td:
    r = Path(td) / "a"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.cpp").write_text(SRC)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=r, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=ENV, capture_output=True, timeout=600)
    s = cli(r, "symbol", "area")
    out["symbol_ranges"] = "L8-10" in s and "L12-14" in s and "L8-14" not in s
    src = cli(r, "symbol", "area", "--source")
    out["source_separate"] = "w * w" in src and "w * h + 7" in src and not any(
        l.strip().startswith("11 ") or l.strip() == "11" for l in src.splitlines())
    o = cli(r, "outline", "src/a.cpp")
    out["outline_ranges"] = "L8-10" in o and "L12-14" in o and "L8-14" not in o
    out["text"] = (s + "\n---\n" + o)[:400]
out["pass"] = out["symbol_ranges"] and out["source_separate"] and out["outline_ranges"]
print(json.dumps(out))
