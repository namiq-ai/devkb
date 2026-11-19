"""#228: two builds of the same tree write identical flow STEP edges (sequence included), whatever the hash seed."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_two_builds_with_different_hash_seeds_give_the_same_edges(tmp_path):
    files = {"pkg/__init__.py": "", "pkg/main.py": "from pkg.a import a1, a2\n\n\ndef main():\n    a1()\n    a2()\n\n\nif __name__ == '__main__':\n    main()\n",
             "pkg/a.py": "".join(f"def a{i}():\n    return b{i}() + c{i}()\n\n\ndef b{i}():\n    return 1\n\n\ndef c{i}():\n    return 2\n\n\n" for i in (1, 2))}
    for rel, t in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(t)
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=tmp_path, check=True)
    out = []
    for seed in ("1", "2", "3"):
        env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore", PYTHONHASHSEED=seed)
        subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(tmp_path)], cwd=tmp_path, env=env,
                       check=True, capture_output=True)
        out.append(sorted(l for l in (tmp_path / ".devkb" / "edges.jsonl").read_text().splitlines() if '"STEP"' in l))
    assert out[0] and out[0] == out[1] == out[2]
