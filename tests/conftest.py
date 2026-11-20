"""Benchmark tests never write run checkouts or templates into the real cache directories (#340)."""
import pytest


@pytest.fixture(autouse=True)
def _bench_dirs_in_tmp(request, tmp_path, monkeypatch):
    if request.module.__name__.startswith("test_bench_"):
        monkeypatch.setenv("POLICY_WORK_DIR", str(tmp_path / "policy-work"))
        monkeypatch.setenv("POLICY_TEMPLATES_DIR", str(tmp_path / "policy-templates"))
