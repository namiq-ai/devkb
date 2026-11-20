"""#364: the files the sdist is made of hold no string of `.release-denylist`, so the `pypi` job's scan (`scripts/check_dist.py`) does
not stop an upload. The 0.2.13 upload was stopped by a private-key marker in a test fixture, and 0.2.14 would have been by a home
directory path in another. The sdist holds `devkb/`, `tests/`, README.md, LICENSE, NOTICE and pyproject.toml (checked on the 0.2.13
sdist); this test packs those tracked files and runs the same scanner on them."""
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SDIST_PATHS = ("devkb/", "tests/")
SDIST_ROOT_FILES = ("README.md", "LICENSE", "NOTICE", "pyproject.toml")


def _scan(archive: Path):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_dist.py"), str(archive)], cwd=ROOT, capture_output=True, text=True)


def test_the_files_the_sdist_is_made_of_hold_no_denylisted_string(tmp_path):
    p = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    if p.returncode:
        pytest.skip("not a git checkout")
    files = [x.decode() for x in p.stdout.split(b"\0") if x]
    mine = [f for f in files if (f.startswith(SDIST_PATHS) or f in SDIST_ROOT_FILES) and (ROOT / f).is_file()]
    assert len(mine) > 100, "the sdist file set looks wrong: " + str(len(mine))
    archive = tmp_path / "devkb-0.0.0.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        for f in mine:
            t.add(ROOT / f, arcname=f"devkb-0.0.0/{f}")
    r = _scan(archive)
    assert r.returncode == 0, "the pypi job would refuse this package:\n" + r.stdout + r.stderr


def test_the_scan_does_refuse_a_denylisted_string(tmp_path):
    """The test above is only worth something if the scan can fail: a package holding a home directory path is refused."""
    src = tmp_path / "f.txt"
    src.write_text("/ho" + "me/someone/project\n")
    bad = tmp_path / "bad-0.0.0.tar.gz"
    with tarfile.open(bad, "w:gz") as t:
        t.add(src, arcname="bad-0.0.0/f.txt")
    assert _scan(bad).returncode != 0
