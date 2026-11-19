"""#224: the release performance check refuses tmpfs and marks a change within noise from the NEW/NEW-again gap."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("perf_release", Path(__file__).resolve().parents[1] / "bench" / "perf_release.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def res(build, query):
    return {"repos": {"r": {"build": [{"secs": s, "peak_mb": 100} for s in build], "graph_mb": 5.0,
                            "queries": {"symbol": {"median_s": query}}}}}


def test_a_change_inside_the_noise_pass_is_marked_and_a_larger_one_is_not():
    out = pr.compare(res([10, 10, 10], 1.0), res([10.5, 10.5, 10.5], 2.0), res([9.8, 9.8, 9.8], 2.02))
    build = next(l for l in out.splitlines() if l.startswith("| build s"))
    sym = next(l for l in out.splitlines() if l.startswith("| symbol s"))
    assert "within noise" in build and "within noise" not in sym and "+101%" in sym


def test_a_memory_backed_work_directory_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "fs_type", lambda p: "tmpfs")
    with pytest.raises(SystemExit, match="memory-backed"):
        pr.refuse_tmpfs(tmp_path)
    monkeypatch.setattr(pr, "fs_type", lambda p: "ext2/ext3")
    pr.refuse_tmpfs(tmp_path)
