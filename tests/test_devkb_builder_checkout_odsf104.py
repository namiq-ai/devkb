"""ODSF-104: a build refuses to write another checkout's graph with this code.

`devkb/build.py --project CODE` takes its extractor CODE from the checkout it
runs in and its TARGET from projects.json. Those are not required to be the same
directory, so a build inside a git worktree rebuilds the main checkout's graph
using the worktree's extractors and config.

It happened three times while this feature was being built — twice by accident
during the ODSF-102/103 landings, and once more while writing this very ticket,
when a worktree still holding the pre-guard build.py clobbered the graph again.
That third one is why the guard lives in `build.py` and not only in a convention.

What made it expensive is that the result looks healthy: the manifest records
the TARGET's HEAD, so a graph built by stale code carries a current commit hash,
a recent timestamp and a plausible node count. The only symptom was the BA
quietly measuring a requirement against 2 specification documents instead of 5.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "devkb_build_under_test", _REPO_ROOT / "devkb" / "build.py",
)
assert _spec and _spec.loader
build_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_mod)

pytestmark = pytest.mark.ticket("ODSF-104")


def _repo(path: Path, text: str = "x") -> None:
    path.mkdir(parents=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.org", "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "f.txt").write_text(text)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", text], cwd=path, check=True, env=env)


class TestTheGuardItself:
    def test_a_matching_checkout_is_allowed(self, tmp_path: Path):
        assert build_mod.check_builder_matches_target(tmp_path, tmp_path) is None

    def test_another_checkout_of_the_same_repository_is_refused(self, tmp_path: Path):
        target, builder = tmp_path / "product", tmp_path / "product-wt"
        _repo(target)
        subprocess.run(["git", "clone", "-q", str(target), str(builder)], check=True)
        msg = build_mod.check_builder_matches_target(target, builder)
        assert msg is not None
        # Both paths must be in the message: the whole failure was not knowing
        # which code had run against which repo.
        assert str(target) in msg and str(builder) in msg
        assert "--allow-foreign-checkout" in msg

    def test_an_unrelated_repository_is_allowed(self, tmp_path: Path):
        # devkb installed on its own analyses any repository: its code is not a stale copy of the target's.
        target, builder = tmp_path / "product", tmp_path / "devkb"
        _repo(target), _repo(builder, "other")
        assert build_mod.check_builder_matches_target(target, builder) is None

    def test_the_comparison_survives_symlinks_and_relative_paths(self, tmp_path: Path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        # A worktree reached through a symlink is still the same checkout;
        # refusing it would make the guard fire on a legitimate build.
        assert build_mod.check_builder_matches_target(link, real) is None

    def test_the_builder_root_is_this_checkout_not_the_cwd(self):
        # Derived from __file__, so invoking the script from anywhere still
        # reports the checkout the code actually came from.
        assert build_mod.BUILDER_ROOT == _REPO_ROOT


class TestTheManifestIdentifiesTheCodeThatRan:
    """Asserted against `manifest_payload()` rather than against whatever
    `.devkb/manifest.json` happens to hold. A test that reads the live graph
    would pass or fail on whether someone rebuilt recently — the same
    drifting-state defect ODSF-095 had to remove from another suite."""

    def test_it_records_the_builder_beside_the_target(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(build_mod, "git_head", lambda root: f"head-of-{Path(root).name}")
        payload = build_mod.manifest_payload("X", tmp_path / "product", 10, 20)
        assert payload["git_head"] == "head-of-product"
        assert payload["builder_git_head"] == f"head-of-{build_mod.BUILDER_ROOT.name}"
        assert payload["builder_root"] == str(build_mod.BUILDER_ROOT)

    def test_the_pre_existing_fields_are_untouched(self, tmp_path: Path):
        # Anything already reading this manifest must keep working.
        payload = build_mod.manifest_payload("ODSF", tmp_path, 4, 5)
        assert {"project", "built_at", "git_head", "node_count", "edge_count"} <= set(payload)
        assert (payload["project"], payload["node_count"], payload["edge_count"]) == ("ODSF", 4, 5)

    def test_a_stale_build_is_now_distinguishable(self, tmp_path: Path, monkeypatch):
        """The whole point: target HEAD and builder HEAD differing is the signal
        that was missing when a worktree overwrote the main graph."""
        monkeypatch.setattr(build_mod, "git_head",
                            lambda root: "target-sha" if "product" in str(root) else "stale-sha")
        payload = build_mod.manifest_payload("X", tmp_path / "product", 1, 1)
        assert payload["git_head"] != payload["builder_git_head"]


class TestTheEscapeHatchStaysOpen:
    def test_an_explicit_flag_permits_a_foreign_build(self, monkeypatch, tmp_path: Path):
        """Running one deliberately is legitimate — the ticket's scope says so —
        so the guard must be a default, not a prohibition."""
        calls: list = []

        class FakeCtx:
            repo_root = tmp_path / "elsewhere"
            devkb_dir = tmp_path / "elsewhere" / ".devkb"

        monkeypatch.setattr(build_mod, "resolve", lambda code: FakeCtx())
        monkeypatch.setattr(build_mod, "check_builder_matches_target",
                            lambda *a, **k: "mismatch")
        # Stop immediately after the guard: this test is about whether the guard
        # lets execution through, not about running every extractor.
        monkeypatch.setattr(build_mod.tickets_git, "extract",
                            lambda ctx: calls.append("ran") or (_ for _ in ()).throw(
                                RuntimeError("reached the extractors")))

        with pytest.raises(ValueError, match="mismatch"):
            build_mod.build("X", allow_foreign_checkout=False)
        assert calls == [], "the guard must refuse BEFORE any extractor runs"

        with pytest.raises(RuntimeError, match="reached the extractors"):
            build_mod.build("X", allow_foreign_checkout=True)
        assert calls == ["ran"]


def test_a_build_written_outside_the_target_is_not_refused(tmp_path: Path, monkeypatch):
    """A benchmark snapshot (DEVKB_DIR) cannot overwrite the target's own graph, so the guard does not apply."""
    target, builder = tmp_path / "product", tmp_path / "product-wt"
    _repo(target)
    subprocess.run(["git", "clone", "-q", str(target), str(builder)], check=True)
    monkeypatch.setattr(build_mod, "BUILDER_ROOT", builder)
    monkeypatch.setenv("DEVKB_DIR", str(tmp_path / "snapshot"))
    graph, out = build_mod.build(str(target))
    assert out == tmp_path / "snapshot" and (out / "manifest.json").exists()
    monkeypatch.delenv("DEVKB_DIR")
    with pytest.raises(ValueError, match="not the project being built"):
        build_mod.build(str(target))
