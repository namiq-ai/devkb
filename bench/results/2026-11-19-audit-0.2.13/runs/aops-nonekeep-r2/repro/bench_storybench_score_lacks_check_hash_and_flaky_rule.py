"""storybench.py (the other benchmark harness feeding release_table.py) still scores with the pre-0.2.13 rules: no
accept_sha256 (#223: mixed hidden-check versions go unnoticed), `pytest -x` with no failed ids and no flaky re-run
(#260), and its checkout never checks that the base suite is green (#221)."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import storybench as sb  # noqa: E402

tmp = Path(tempfile.mkdtemp())
sb.B = tmp
env = dict(os.environ, GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@e.com", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@e.com")
w = tmp / "work" / "7-devkb-r1"
(w / ".venv" / "bin").mkdir(parents=True)
py = w / ".venv" / "bin" / "python"
py.write_text('#!/bin/sh\ncase "$1" in -m) echo "1 failed"; exit 1;; *) echo \'{"pass": true}\';; esac\n')
py.chmod(0o755)
for c in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
    subprocess.run(["git", *c], cwd=w, check=True, capture_output=True, env=env)
(w / ".bench-base").write_text(subprocess.run(["git", "rev-parse", "HEAD"], cwd=w, capture_output=True, text=True).stdout.strip())
out = tmp / "runs" / "7-devkb-r1"
out.mkdir(parents=True)
(out / "end").write_text(json.dumps({"exit": 0, "seconds": 1}))
(out / "stream.jsonl").write_text("{}\n")
(tmp / "accept").mkdir()
(tmp / "accept" / "7.py").write_text("")
sb.score("7")
row = json.loads((tmp / "results-7.jsonl").read_text().splitlines()[0])
missing = [k for k in ("accept_sha256", "suite_failed", "suite_flaky", "base_green") if k not in row]
print("keys a scored row must carry that this one lacks:", missing)
print("expected: storybench rows carry the check's hash, the failed ids and flaky list, like policybench rows")
sys.exit(1 if missing else 0)
