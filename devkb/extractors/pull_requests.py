"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers feed one set of records, and the graph is emitted once from the merged result:

  offline (always)  one `git log` pass. A merge commit `Merge pull request #N from <owner>/<branch>` gives PullRequest
                    PR-N and MERGES to the merge commit and the commits it brought in (`M^1..M^2`); a squash commit
                    whose subject ends `(#N)` gives PR-N and MERGES to that commit. Both at confidence 0.9: a subject is
                    text a person can edit. A closing keyword (`Fixes #N`) in the commit messages of a pull request gives
                    CLOSES at 0.7 to a Ticket GH-N marked `unverified`, because offline `#N` might be a pull request.
  online (opt-in)   devkb/github.py reads the API. Its commit lists replace the offline MERGES edges (confidence 1.0),
                    its closing records replace the offline CLOSES edges, every issue becomes a Ticket, and a commit
                    message mentioning `#N` of an issue gives REFERENCES (0.8). When the API cannot be reached the
                    offline layer stands and the report says what is missing.

Not stored: descriptions, review text, and (unless `"github": {"authors": true}`) author logins.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from devkb import github
from devkb.extractors.source_baseline import DEFAULT_SINCE
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext, load_config

MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from (\S+)")
SQUASH_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
CLOSING = re.compile(r"(?<![\w/])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?[ \t]+#(\d+)\b", re.IGNORECASE)
HASH_MENTION = re.compile(r"(?<![\w/&#])#(\d+)\b")

OFFLINE_MERGES = 0.9
OFFLINE_CLOSES = 0.7
HASH_REFERENCE = 0.8

#: hosted-issue labels that decide ticket_type when the repository uses no issue types
_LABEL_TYPES = {"bug": "BUG", "epic": "EPIC", "enhancement": "FEATURE", "feature": "FEATURE"}


@dataclass
class PR:
    number: int
    props: dict = field(default_factory=dict)
    source: str = ""
    # sha -> (source, confidence, evidence_ref)
    merges: dict[str, tuple[str, float, str]] = field(default_factory=dict)
    # issue number -> (source, confidence, unverified, evidence_ref)
    closes: dict[int, tuple[str, float, bool, str]] = field(default_factory=dict)


def _git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read_log(repo_root: Path, since: str = DEFAULT_SINCE) -> list[dict]:
    """Every commit in the window: hash, parents, committer date, subject and the full message."""
    out = _git(repo_root, "log", "--all", f"--since={since}", "--format=%H%x1f%P%x1f%cI%x1f%B%x1e")
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f", 3)
        if len(parts) != 4:
            continue
        sha, parents, date, message = parts
        commits.append({"hash": sha.strip(), "parents": parents.split(), "date": date, "message": message.strip(),
                        "subject": message.strip().split("\n", 1)[0]})
    return commits


def _closing_numbers(text: str) -> set[int]:
    return {int(n) for n in CLOSING.findall(text)}


def hosted_ticket_type(issue_type: str | None, labels: list[str], has_children: bool) -> str:
    if issue_type:
        t = re.sub(r"[^A-Z0-9]+", "_", issue_type.upper()).strip("_")
    else:
        t = "ISSUE"
        for label in labels:
            key = re.split(r"[:/]", label.lower())[-1].strip()
            if key in _LABEL_TYPES:
                t = _LABEL_TYPES[key]
                break
    return "EPIC" if t == "ISSUE" and has_children else t


def offline_records(ctx: ProjectContext, commits: list[dict]) -> dict[int, PR]:
    """Pull requests recoverable from git alone."""
    root = ctx.repo_root
    known = {c["hash"] for c in commits}
    remote = github.origin(root)
    url_base = f"https://{remote[0]}/{remote[1]}/{remote[2]}/pull/" if remote and github.is_github_host(remote[0]) else None
    prs: dict[int, PR] = {}
    squash_seen: dict[int, dict] = {}
    by_hash = {x["hash"]: x for x in commits}
    for c in sorted(commits, key=lambda c: c["date"]):
        m = MERGE_SUBJECT.match(c["subject"])
        if m and len(c["parents"]) == 2:
            n = int(m[1])
            pr = prs.setdefault(n, PR(n, source="git-merge-subject"))
            body = [ln.strip() for ln in c["message"].split("\n")[1:] if ln.strip()]
            branch = m[2].split("/", 1)[-1]
            pr.props.update({"number": n, "title": body[0] if body else c["subject"], "state": "merged", "merged_at": c["date"],
                             "head": branch, "merge_style": "merge", **({"url": f"{url_base}{n}"} if url_base else {})})
            pr.merges[c["hash"]] = ("git-merge-subject", OFFLINE_MERGES, c["subject"])
            brought = _git(root, "rev-list", f"{c['hash']}^1..{c['hash']}^2").split()
            text = [c["message"]]
            for h in brought:
                if h in known:
                    pr.merges[h] = ("git-merge-subject", OFFLINE_MERGES, f"git rev-list {c['hash'][:10]}^1..{c['hash'][:10]}^2")
                    text.append(by_hash[h]["message"])
            for num in sorted(set().union(*(_closing_numbers(t) for t in text)) - {n}):
                pr.closes.setdefault(num, ("git-closing-keyword", OFFLINE_CLOSES, True, f"closing keyword in a commit of PR-{n}"))
            continue
        s = SQUASH_SUBJECT.search(c["subject"])
        if s and len(c["parents"]) <= 1:
            # a backport or cherry-pick repeats the subject; the earliest commit is the merge itself
            squash_seen.setdefault(int(s[1]), c)
    for n, c in squash_seen.items():
        pr = prs.setdefault(n, PR(n, source="git-squash-subject"))
        if "merge_style" not in pr.props:
            pr.props.update({"number": n, "title": SQUASH_SUBJECT.sub("", c["subject"]).rstrip(), "state": "merged",
                             "merged_at": c["date"], "merge_style": "squash", **({"url": f"{url_base}{n}"} if url_base else {})})
        pr.merges[c["hash"]] = ("git-squash-subject", OFFLINE_MERGES, c["subject"])
        for num in sorted(_closing_numbers(c["message"]) - {n}):
            pr.closes.setdefault(num, ("git-closing-keyword", OFFLINE_CLOSES, True, f"closing keyword in the commit of PR-{n}"))
    return prs


def _apply_online(prs: dict[int, PR], snap: github.Snapshot, known_commits: set[str]) -> tuple[dict[int, dict], int]:
    """Fold the API's answer into the offline records. Returns the issue records by number and the count of API commits
    that are not in the local history (open or force-pushed branches, rebased copies)."""
    foreign = 0
    for n, rec in snap.pulls.items():
        pr = prs.setdefault(n, PR(n, source="github-api"))
        for k in ("title", "state", "merged_at", "base", "head", "labels", "url", "author"):
            if rec.get(k) is not None:
                pr.props[k] = rec[k]
        pr.props["number"] = n
        if "commits" in rec:
            api: dict[str, str] = {sha: f"GET pulls/{n}/commits" for sha in rec["commits"]}
            if rec.get("state") == "merged" and rec.get("merge_commit_sha"):
                api.setdefault(rec["merge_commit_sha"], f"merge_commit_sha of PR-{n}")
            foreign += sum(1 for sha in api if sha not in known_commits)
            if len(rec["commits"]) < github.COMMITS_CAP:  # a complete list can contradict; a capped one cannot
                pr.merges = {h: v for h, v in pr.merges.items() if h in api}
            for sha, ev in api.items():
                if sha in known_commits:
                    pr.merges[sha] = ("github-api", 1.0, ev)
        if "closes" in rec:
            api_closes = set(rec["closes"])
            pr.closes = {k: v for k, v in pr.closes.items() if k in api_closes}
            for num in api_closes:
                pr.closes[num] = ("github-closing-references", 1.0, False, f"GitHub's closing record for PR-{n}")
    # an offline "Fixes #N" whose N is a pull request is not a ticket link
    if snap.pulls_complete:
        for pr in prs.values():
            pr.closes = {k: v for k, v in pr.closes.items() if k not in snap.pulls}
    return {n: r for n, r in snap.issues.items()}, foreign


def extract(ctx: ProjectContext, online: bool = False, since: str = DEFAULT_SINCE) -> tuple[DevKBGraph, dict]:
    """The pull-request graph and the report written to the manifest (empty when the online layer was not asked for)."""
    g = DevKBGraph()
    commits = read_log(ctx.repo_root, since)
    known = {c["hash"] for c in commits}
    prs = offline_records(ctx, commits)
    issues: dict[int, dict] = {}
    report: dict = {}
    snap = None
    if online:
        report, snap = _run_online(ctx)
        if snap is not None:
            issues, foreign = _apply_online(prs, snap, known)
            report["commits_not_in_local_history"] = foreign
    authors = bool((load_config(ctx.repo_root).get("github") or {}).get("authors"))

    for n, rec in issues.items():
        key = f"GH-{n}"
        parent = rec.get("parent")
        ttype = hosted_ticket_type(rec.get("type"), rec.get("labels") or [], bool(rec.get("sub_issues")))
        g.add_node("Ticket", key, source="github-issues", title=rec.get("title"), type=ttype, ticket_type=ttype,
                   status=(rec.get("state") or "").upper(), state=rec.get("state"), state_reason=rec.get("state_reason"),
                   labels=rec.get("labels"), milestone=rec.get("milestone"), url=rec.get("url"),
                   created_at=rec.get("created_at"), closed_at=rec.get("closed_at"), number=n,
                   **({"author": rec["author"]} if authors and rec.get("author") else {}))
        if parent and parent in issues:
            g.add_edge("CHILD_OF", "Ticket", key, "Ticket", f"GH-{parent}", source="github-sub-issues", confidence=1.0,
                       evidence_ref=f"sub-issue of #{parent}")
    if snap is not None:
        for n, info in snap.issue_titles.items():
            if n not in issues:
                g.add_node("Ticket", f"GH-{n}", source="github-issues", title=info.get("title"), ticket_type="ISSUE",
                           type="ISSUE", status=(info.get("state") or "").upper(), state=info.get("state"), url=info.get("url"), number=n)

    unverified = 0
    ticket_keys = {t.natural_key for t in g.nodes("Ticket")}
    for n in sorted(prs):
        pr = prs[n]
        if not pr.props and not pr.merges:
            continue
        g.add_node("PullRequest", f"PR-{n}", source=pr.source, **pr.props)
        for sha, (src, conf, ev) in sorted(pr.merges.items()):
            g.add_node("Commit", sha, source="git-pr-layer")
            g.add_edge("MERGES", "PullRequest", f"PR-{n}", "Commit", sha, source=src, confidence=conf, evidence_ref=ev)
        for num, (src, conf, unver, ev) in sorted(pr.closes.items()):
            if unver:
                unverified += 1
            if f"GH-{num}" not in ticket_keys:
                # a stub: the issue was not read from the API, so it carries only its number
                ticket_keys.add(f"GH-{num}")
                g.add_node("Ticket", f"GH-{num}", source="git-closing-keyword" if unver else "github-issues",
                           ticket_type="ISSUE", type="ISSUE", number=num, **({"unverified": True} if unver else {}))
            g.add_edge("CLOSES", "PullRequest", f"PR-{n}", "Ticket", f"GH-{num}", source=src, confidence=conf, evidence_ref=ev,
                       extra={"unverified": True} if unver else {})
    # commit messages that mention an issue by number; only the online layer can tell an issue from a pull request
    if issues:
        for c in commits:
            for num in sorted({int(x) for x in HASH_MENTION.findall(c["message"])}):
                if num in issues and num not in prs:
                    g.add_node("Commit", c["hash"], source="git-pr-layer")
                    g.add_edge("REFERENCES", "Commit", c["hash"], "Ticket", f"GH-{num}", source="git-hash-mention",
                               confidence=HASH_REFERENCE, evidence_ref=f"#{num} in the commit message")
    if report:
        report["unverified_closing_links"] = unverified
    return g, report


def _run_online(ctx: ProjectContext) -> tuple[dict, "github.Snapshot | None"]:
    cfg = load_config(ctx.repo_root).get("github") or {}
    remote = github.origin(ctx.repo_root)
    if remote is None or not github.is_github_host(remote[0]):
        why = "the origin remote is not a GitHub repository" if remote else "the repository has no origin remote"
        return {"enabled": True, "status": "unavailable", "problems": [why]}, None
    host, owner, repo = remote
    client = github.Client(host, owner, repo, github.find_token(host), int(cfg.get("max_requests") or github.DEFAULT_MAX_REQUESTS))
    authors = bool(cfg.get("authors"))
    cache = github.Cache(ctx.devkb_dir / "github", f"{host}/{owner}/{repo}", authors)
    snap = github.fetch(client, cache, authors)
    return snap.report(authors), snap


def online_requested(ctx: ProjectContext, flag: bool = False) -> bool:
    """The flag, or `{"github": {"enabled": true}}` in devkb.json. Never on by default."""
    return bool(flag or (load_config(ctx.repo_root).get("github") or {}).get("enabled"))


def describe(report: dict) -> list[str]:
    """Lines for the build's stderr: what the online layer did and what it could not fetch."""
    if not report:
        return []
    head = (f"devkb build: github {report.get('repo', '')}: {report['status']} — {report.get('pull_requests', 0)} pull requests, "
            f"{report.get('issues', 0)} issues, {report.get('requests', 0)} requests, {report.get('cached_items', 0)} from cache")
    return [head] + [f"devkb build:   could not fetch — {p}" for p in report.get("problems", [])]


if __name__ == "__main__":  # pragma: no cover
    print(__doc__, file=sys.stderr)
