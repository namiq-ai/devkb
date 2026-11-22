"""#122 (SPEC-DKB-004 F7): C and C++ are in the CI language check, each with at least three pinned public repositories and minimums."""
from __future__ import annotations

from pathlib import Path

import yaml

REG = yaml.safe_load((Path(__file__).resolve().parents[1] / "bench" / "languages.yaml").read_text())["languages"]


def test_c_and_cpp_have_three_pinned_repositories_each_with_minimums():
    for lang in ("c", "cpp"):
        repos = REG[lang]["repos"]
        assert len(repos) >= 3, lang
        assert REG[lang]["source"] == "cpp-symbols"
        for r in repos:
            assert len(r["commit"]) == 40 and r["url"].startswith("https://github.com/"), r["id"]
            assert r["min_symbols"] > 0 and r["min_calls"] > 0 and "min_tests" in r, r["id"]
    ids = [r["id"] for lang in ("c", "cpp") for r in REG[lang]["repos"]]
    assert len(ids) == len(set(ids)), "one repository counts toward one language"
