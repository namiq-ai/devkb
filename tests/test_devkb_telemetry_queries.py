"""#127: every query devkb answers is recorded in .devkb telemetry, command line included, with what was asked."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import process_api, service  # noqa: E402
from devkb.packs import Packer, logged_pack  # noqa: E402

FILES = {"pkg/__init__.py": "", "pkg/alpha.py": "def extract(x):\n    return x\n",
         "pkg/use.py": "from pkg import alpha\n\n\ndef go():\n    return alpha.extract(1)\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    return root


def lines(root: Path) -> list[dict]:
    f = root / ".devkb" / service.TELEMETRY_NAME
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def cli(root: Path, *args: str, **env) -> str:
    e = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore", **env)
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *args, "--project", str(root)], cwd=root, env=e,
                          capture_output=True, text=True, timeout=120).stdout


def test_a_command_line_query_is_recorded_with_what_was_asked(repo):
    n = len(lines(repo))
    assert "extract" in cli(repo, "symbol", "extract")
    new = lines(repo)[n:]
    assert len(new) == 1 and new[0]["tool"] == "symbol" and new[0]["source"] == "cli"
    assert new[0]["args"]["query"] == "extract" and new[0]["bytes"] > 0 and new[0]["ok"]


def test_a_server_call_is_recorded_as_mcp(repo):
    n = len(lines(repo))
    process_api.ProcessAPI(str(repo)).call("uses", name="extract")
    new = lines(repo)[n:]
    assert [(l["tool"], l["source"], l["args"]["name"]) for l in new] == [("uses", "mcp", "extract")]


def test_a_pack_is_recorded_from_both_paths(repo):
    n = len(lines(repo))
    cli(repo, "pack", "change", "extract")
    logged_pack(Packer(process_api.ProcessAPI(str(repo))), "file", "pkg/use.py")
    new = lines(repo)[n:]
    assert [(l["tool"], l["source"], l["args"]["kind"]) for l in new] == [("pack", "cli", "change"), ("pack", "mcp", "file")]


def test_long_arguments_are_cut(repo):
    n = len(lines(repo))
    process_api.ProcessAPI(str(repo)).call("search_docs", query="x" * 500)
    assert len(lines(repo)[n]["args"]["query"]) == 200


def test_the_switch_turns_recording_off(repo):
    n = len(lines(repo))
    cli(repo, "symbol", "extract", DEVKB_TELEMETRY="0")
    assert len(lines(repo)) == n
