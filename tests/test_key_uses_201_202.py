"""#201: a prefix match does not hide a name's string-key uses. #202: `"k" in d` and `d["k"] += 1` are reads,
`d.update(k=...)` / `dict(k=...)` are writes, and os.environ lookups are not record keys."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ('import os\n\n\ndef write(rec):\n    rec["status"] = "ok"\n    rec["count"] += 1\n    rec.update(owner="me")\n'
       '    return dict(status="new")\n\n\ndef read(rec):\n    if "status" in rec:\n        return rec["status"]\n'
       '    return rec.get("status"), os.environ.get("status")\n')


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    r = tmp_path_factory.mktemp("r201")
    (r / "app.py").write_text(APP)
    (r / "other.py").write_text("def status_of(job):\n    return job\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=r, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=r, env=env, check=True, capture_output=True)
    return r


def symbol(r, name, *extra):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "symbol", name, *extra, "--project", str(r)], cwd=r, env=env,
                          capture_output=True, text=True).stdout


def lines(js, name, how):
    return sorted(ln for k in js.get("key_uses", []) if k.get("key", name) == name for u in k.get(how + "s", k.get(how, [])) for ln in
                  ([u] if isinstance(u, int) else [u.get("line", 0)] if isinstance(u, dict) else []))


def test_a_prefix_match_still_shows_the_key_uses(repo):
    out = symbol(repo, "status")
    assert "status_of" in out and "string key" in out and "write" in out


def test_membership_and_augmented_reads_keyword_writes_and_no_environ(repo):
    out = symbol(repo, "status")
    assert "12" in out                                  # `if "status" in rec` (line 12) is a read
    assert "environ" not in json.dumps(json.loads(symbol(repo, "status", "--json")).get("key_uses", []))
    count = symbol(repo, "count")
    assert "read" in count and "write" in count         # rec["count"] += 1
    assert "no symbol named" not in symbol(repo, "owner") or "string key" in symbol(repo, "owner")
