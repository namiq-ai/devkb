"""The PR gate (#316): from a PR's facts and its review's findings, one decision. No side effects, no merge here.

    merge        the owner's own PR, every gate holds, and this is the owner's identity on an allowed host
    rework       the owner's own PR, a gate fails or the review is not clean: do not merge, label needs-rework, post findings
    review-only  anyone else's PR, a fork, or a merge attempted from the wrong identity or host: post the review, never merge

Usage: python bench/review/gate.py PR FINDINGS.json   (prints the decision as JSON; acting on it, and the review that makes FINDINGS.json, are the caller's job)
"""
from __future__ import annotations

import fnmatch
import json
import os
import socket
import subprocess
import sys

OWNER = "hungle-namiq"
# A PR touching these is never merged by the gate (owner decides): it is sent to rework with the reason.
NEVER_MERGE = (".github/workflows/*", "ops/triage/*", "pyproject.toml", "MANIFEST.in", "docs/specs/*", "docs/adr/*",
               "docs/RELEASING.md", "scripts/release*")
BLOCKING = ("high", "medium")


def decide(pr: dict, findings: list[dict], whoami: str, host: str, allowed_hosts: tuple[str, ...] | list[str],
           owner: str = OWNER) -> dict:
    """pr: {author, is_fork, files, ci_green, suite_green, hidden_check (True/False/None), head}.
    findings: reproduced findings, each {severity, open (bool), arms (the review arms that found it: severity per arm)}."""
    own = pr.get("author") == owner and not pr.get("is_fork")
    if not own:
        return {"action": "review-only", "reasons": ["not the owner's own PR: reviewed and reported, never merged"]}
    why: list[str] = []
    if not pr.get("ci_green"):
        why.append("CI is not green")
    if not pr.get("suite_green"):
        why.append("the full suite is not green")
    if pr.get("hidden_check") is False:
        why.append("the ticket's hidden check fails")
    for f in findings:
        if f.get("open", True) and f.get("severity") in BLOCKING:
            why.append(f"open {f['severity']} finding: {f.get('title', '?')}")
        sev = {v for v in (f.get("severity_by_arm") or {}).values() if v}
        if len(sev) > 1:
            why.append(f"the two reviews disagree on the severity of: {f.get('title', '?')}")
    guarded = sorted({p for p in pr.get("files", []) for g in NEVER_MERGE if fnmatch.fnmatch(p, g)})
    if guarded:
        why.append("touches a path the gate never merges: " + ", ".join(guarded))
    if why:
        return {"action": "rework", "reasons": why}
    if whoami != owner or host not in allowed_hosts:
        return {"action": "review-only", "reasons": [f"every gate holds, but a merge needs {owner}'s own gh identity on an "
                                                     f"allowed host (this is {whoami} on {host})"]}
    return {"action": "merge", "reasons": ["every gate holds"]}


def _gh(*a: str) -> str:
    return subprocess.run(["gh", *a], capture_output=True, text=True, check=True, timeout=60).stdout


def pr_facts(n: str) -> dict:
    j = json.loads(_gh("pr", "view", n, "--json", "author,isCrossRepository,files,headRefOid,statusCheckRollup"))
    runs = j.get("statusCheckRollup") or []
    return {"author": j["author"]["login"], "is_fork": j["isCrossRepository"], "head": j["headRefOid"],
            "files": [f["path"] for f in j["files"]],
            "ci_green": bool(runs) and all(r.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED") for r in runs),
            "suite_green": None, "hidden_check": None}      # the review harness fills these from its own run


def main(argv: list[str]) -> int:
    if len(argv) < 3:                                   # no review, no decision: an empty list would read as "clean"
        print("usage: gate.py PR FINDINGS.json  (the review's reproduced findings; [] only when it found none)", file=sys.stderr)
        return 2
    pr = pr_facts(argv[1])
    findings = json.load(open(argv[2]))
    hosts = [h for h in os.environ.get("DEVKB_REVIEW_HOSTS", "").split(",") if h]   # none set: the gate never merges
    print(json.dumps(decide({**pr, "suite_green": pr["ci_green"]}, findings, _gh("api", "user", "--jq", ".login").strip(),
                            socket.gethostname(), hosts), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
