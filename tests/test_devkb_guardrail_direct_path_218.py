"""#218 (SPEC-DKB-007 S5) and #214's added scope: every answer's hash, size and first line are logged (and kept in full
with DEVKB_GUARDRAIL_KEEP=1); D1 (DEVKB_GUARDRAIL_TEACH=1) ends an answer with the devkb command that gives it; D2
(DEVKB_GUARDRAIL_OUTLINE=1) gives the first whole-file Read of a long code file its outline. Both are off by default."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r218")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("def compute(x):\n    return x * 2\n")
    (root / "pkg" / "app.py").write_text("from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n")
    (root / "pkg" / "big.py").write_text("".join(f"def g{i}():\n    return {i}\n\n\n" for i in range(40)))
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


_n = [0]


def hook(repo, home, tool, inp, **extra):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), **extra)
    out = ""
    for j, (t, i) in enumerate((("Bash", {"command": "ls"}), (tool, inp))):
        ev = {"tool_name": t, "cwd": str(repo), "session_id": f"s218-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}", "tool_input": i}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    return h, [r for r in rows if r["session"] == f"s218-{_n[0]}" and r.get("action") != "remind"]


def text(h):
    return h.get("permissionDecisionReason", "") + h.get("additionalContext", "")


def test_every_answer_is_logged_by_hash_size_and_first_line_and_kept_only_when_asked(repo, tmp_path):
    h, rows = hook(repo, tmp_path, "Bash", {"command": "grep -rn compute pkg/"})
    r = rows[-1]
    assert r["answer_chars"] == len(text(h)) and len(r["answer_sha1"]) == 40 and "pkg/" in r["answer_head"]
    keep = tmp_path / ".claude" / "hooks" / ".devkb-guardrail-answers"
    assert not keep.exists()
    h, rows = hook(repo, tmp_path, "Bash", {"command": "grep -rn compute pkg/"}, DEVKB_GUARDRAIL_KEEP="1")
    assert (keep / f"{rows[-1]['answer_sha1']}.txt").read_text() == text(h)


def test_teach_is_off_by_default_and_adds_one_line_when_on(repo, tmp_path):
    plain, _ = hook(repo, tmp_path, "Bash", {"command": "grep -rn compute pkg/"})
    taught, _ = hook(repo, tmp_path, "Bash", {"command": "grep -rn compute pkg/"}, DEVKB_GUARDRAIL_TEACH="1")
    assert "Next time ask devkb" not in text(plain)
    assert text(taught) == text(plain).rstrip() + "\nNext time ask devkb directly: `devkb uses compute --project .`"


def test_outline_on_first_open_is_off_by_default_and_once_per_file_when_on(repo, tmp_path):
    read = {"file_path": str(repo / "pkg" / "big.py")}
    off, _ = hook(repo, tmp_path, "Read", read)
    assert not off
    home = tmp_path / "on"
    on, rows = hook(repo, home, "Read", read, DEVKB_GUARDRAIL_OUTLINE="1")
    assert "L1-2 function g0" in text(on) and rows[-1]["action"] == "outline-on-open"
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), DEVKB_GUARDRAIL_OUTLINE="1")
    ev = {"tool_name": "Read", "cwd": str(repo), "session_id": f"s218-{_n[0]}", "tool_use_id": "again", "tool_input": read}
    again = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    assert not again.strip()                                     # the same file in the same session: once
    short, _ = hook(repo, home, "Read", {"file_path": str(repo / "pkg" / "core.py")}, DEVKB_GUARDRAIL_OUTLINE="1")
    assert not short                                             # a short file is read faster than its outline
