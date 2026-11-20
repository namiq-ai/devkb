"""#316: the gate's decision for each rule: merge, rework, review-only."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "review"))
g = importlib.import_module("gate")

HOST = ["this-host"]
OK = {"author": "hungle-namiq", "is_fork": False, "files": ["devkb/x.py"], "ci_green": True, "suite_green": True,
      "hidden_check": None}


def d(pr=None, findings=(), who="hungle-namiq", host="this-host"):
    return g.decide({**OK, **(pr or {})}, list(findings), who, host, HOST)


def test_an_own_clean_pr_on_the_owners_host_merges():
    assert d()["action"] == "merge"


def test_someone_elses_pr_is_reviewed_and_never_merged_even_when_clean():
    assert d({"author": "stranger"})["action"] == "review-only"


def test_a_fork_pr_by_the_owner_name_is_review_only():
    assert d({"is_fork": True})["action"] == "review-only"


def test_a_red_ci_suite_or_hidden_check_is_rework():
    for pr in ({"ci_green": False}, {"suite_green": False}, {"hidden_check": False}):
        assert d(pr)["action"] == "rework", pr


def test_an_open_high_or_medium_finding_is_rework_a_low_or_closed_one_is_not():
    assert d(findings=[{"severity": "high", "title": "t"}])["action"] == "rework"
    assert d(findings=[{"severity": "medium", "title": "t"}])["action"] == "rework"
    assert d(findings=[{"severity": "low", "title": "t"}])["action"] == "merge"
    assert d(findings=[{"severity": "high", "open": False}])["action"] == "merge"


def test_arms_disagreeing_on_severity_is_rework():
    f = {"severity": "low", "title": "t", "severity_by_arm": {"devkb": "low", "nodevkb": "medium"}}
    assert d(findings=[f])["action"] == "rework"


def test_guarded_paths_are_never_merged():
    for p in (".github/workflows/ci.yml", "pyproject.toml", "docs/specs/SPEC-DKB-008.md", "docs/adr/x.md"):
        r = d({"files": ["devkb/x.py", p]})
        assert r["action"] == "rework" and p in r["reasons"][0], p


def test_a_merge_from_another_identity_or_host_is_review_only():
    assert d(who="someone-else")["action"] == "review-only"
    assert d(host="other-host")["action"] == "review-only"
    assert g.decide(OK, [], "hungle-namiq", "this-host", [])["action"] == "review-only"   # no allowed host configured
