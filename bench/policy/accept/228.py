"""#228 on a finished checkout: two builds of the same tree with different hash seeds write identical nodes and edges,
flow STEP sequences included."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    files = {"pkg/__init__.py": "", "pkg/main.py": "from pkg.a import a1, a2\n\n\ndef main():\n    a1()\n    a2()\n\n\nif __name__ == '__main__':\n    main()\n",
             "pkg/a.py": "".join(f"def a{i}():\n    return b{i}() + c{i}() + d{i}()\n\n\ndef b{i}():\n    return 1\n\n\ndef c{i}():\n    return 2\n\n\ndef d{i}():\n    return 3\n\n\n" for i in (1, 2))}
    for rel, t in files.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(t)
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    runs = []
    for seed in ("11", "22", "33"):
        env = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore", PYTHONHASHSEED=seed)
        subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=env, capture_output=True, timeout=600)
        runs.append((sorted((r / ".devkb" / "edges.jsonl").read_text().splitlines()),
                     sorted(l for l in (r / ".devkb" / "nodes.jsonl").read_text().splitlines() if '"built' not in l)))
    steps = [l for l in runs[0][0] if '"STEP"' in l]
    out = {"has_steps": bool(steps), "edges_same": runs[0][0] == runs[1][0] == runs[2][0], "nodes_same": runs[0][1] == runs[1][1] == runs[2][1]}
out["pass"] = all(out.values())
print(json.dumps(out))
