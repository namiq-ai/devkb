"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers feed one set of nodes:

  offline   always on, from one `git log` pass. A merge commit `Merge pull request #N from owner/branch` and a squash
            commit whose subject ends `(#N)` name their pull request; a closing keyword in a pull request's commit
            messages gives a low-confidence CLOSES whose target is marked unverified.
  online    only when asked for (`devkb build --github`, or devkb.json `"github": {"enabled": true}`). GitHub's own
            commit lists and closing references replace the offline guesses, and hosted issues become Ticket nodes.

A repository whose `origin` is not a GitHub host gets no new nodes. Descriptions, review text and author logins are
never read from the API, and the owner in `Merge pull request #N from owner/branch` is dropped (it is the author's or
fork's login): the branch name is all that is kept. See devkb/github.py for the API side.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from devkb import github
from devkb.extractors.source_baseline import DEFAULT_SINCE
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

MERGE_SOURCE, SQUASH_SOURCE = "git-merge-subject", "git-squash-subject"
OFFLINE_CONFIDENCE = 0.9
CLOSES_OFFLINE_CONFIDENCE = 0.7
MENTION_CONFIDENCE = 0.8
MAX_BROUGHT_IN = 1000           # commits one merge may bring in before the list is not trusted

_MERGE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_CLOSE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?[ \t]+(#\d+(?:[ \t]*(?:,|and|&)[ \t]*#\d+)*)", re.I)
_MENTION = re.compile(r"(?<![\w/&#])#(\d+)\b")
_NUM = re.compile(r"#(\d+)")


@dataclass
class GitCommit:
    sha: str
    parents: list[str]
    date: str
    committed: str
    subject: str
    body: str


@dataclass
class OfflinePR:
    number: int
    title: str = ""
    head: str | None = None
    merge_style: str | None = None
    merged_at: str = ""
    merge_commit: str = ""
    #: sha -> source of the claim
    commits: dict[str, str] = field(default_factory=dict)
    closes: set[int] = field(default_factory=set)
    too_large: bool = False      # a merge that brought in more than MAX_BROUGHT_IN commits: only the merge is linked


# ── offline ──────────────────────────────────────────────────────────────────────────────
def read_log(repo_root: Path, since: str = DEFAULT_SINCE) -> list[GitCommit]:
    try:
        out = subprocess.run(
            ["git", "log", "--all", f"--since={since}", "-z", "--date=short", "--format=%H%x1f%P%x1f%ad%x1f%cI%x1f%s%x1f%b"],
            cwd=str(repo_root), capture_output=True, text=True, errors="replace", timeout=600).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    commits = []
    for rec in out.split("\0"):
        parts = rec.strip("\n").split("\x1f", 5)
        if len(parts) == 6 and parts[0]:
            commits.append(GitCommit(parts[0], parts[1].split(), parts[2], parts[3], parts[4], parts[5]))
    return commits


def brought_in(repo_root: Path, merge: str) -> list[str] | None:
    """The commits a merge commit brought in: `git rev-list <merge>^1..<merge>^2`. None when there are more than
    MAX_BROUGHT_IN: such a list is not trusted, and the build reports the pull request instead of linking nothing
    silently."""
    try:
        out = subprocess.run(["git", "rev-list", f"{merge}^1..{merge}^2"], cwd=str(repo_root), capture_output=True,
                             text=True, timeout=60).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []
    return out if len(out) <= MAX_BROUGHT_IN else None


def closing_numbers(text: str) -> set[int]:
    return {int(n) for m in _CLOSE.finditer(text) for n in _NUM.findall(m.group(1))}


def scan(commits: list[GitCommit], repo_root: Path,
         brought: Callable[[Path, str], list[str]] = brought_in) -> dict[int, OfflinePR]:
    by_sha = {c.sha: c for c in commits}
    prs: dict[int, OfflinePR] = {}
    # oldest first, so the first commit that names a pull request supplies its title and date
    for c in sorted(commits, key=lambda c: c.committed):
        m = _MERGE.match(c.subject)
        members: list[str] = []
        listed: list[str] | None = []
        if m and len(c.parents) >= 2:
            n, style, source = int(m.group(1)), "merge", MERGE_SOURCE
            title = next((ln.strip() for ln in c.body.splitlines() if ln.strip()), "")
            head = m.group(2).split("/", 1)[-1]      # drop the owner: it is a login
            listed = brought(repo_root, c.sha)
            members = [s for s in (listed or []) if s in by_sha and s != c.sha]
        else:
            m = _SQUASH.search(c.subject)
            if not m or len(c.parents) != 1:
                continue
            n, style, source = int(m.group(1)), "squash", SQUASH_SOURCE
            title, head = c.subject[:m.start()].rstrip(), None
        pr = prs.setdefault(n, OfflinePR(n))
        if style == "merge" and listed is None:
            pr.too_large = True
        if not pr.merge_commit:
            pr.title, pr.head, pr.merge_style = title, head, style
            pr.merged_at, pr.merge_commit = c.committed, c.sha
        pr.commits.setdefault(c.sha, source)
        for s in members:
            pr.commits.setdefault(s, source)
        for sha in [c.sha, *members]:
            pr.closes |= closing_numbers(by_sha[sha].subject + "\n" + by_sha[sha].body)
    for n, pr in prs.items():
        pr.closes.discard(n)
    return prs


# ── building the graph ───────────────────────────────────────────────────────────────────
def _gh(n: int) -> str:
    return f"GH-{n}"


def _pr(n: int) -> str:
    return f"PR-{n}"


def build_graph(remote: github.Remote, commits: list[GitCommit], offline: dict[int, OfflinePR],
                online: github.Online | None, authors: bool = False) -> DevKBGraph:
    g = DevKBGraph()
    known = {c.sha: c for c in commits}
    prs_online = online.prs if online else {}
    issues_online = online.issues if online else {}
    # One number sequence per repository: when GitHub returns N as an issue, a `(#N)` subject named that issue, not a
    # pull request, so the offline guess PR-N is dropped and the issue kept.
    pr_numbers = (set(offline) - set(issues_online)) | set(prs_online)

    def commit_node(sha: str) -> None:
        c = known[sha]
        g.add_node("Commit", sha, source="git", short_hash=sha[:10], date=c.date, subject=github.public_subject(c.subject, authors))

    # ── hosted issues ──
    for n, rec in sorted(issues_online.items()):
        if n in pr_numbers:      # one sequence per repository: an issue and a pull request never share a number
            continue
        g.add_node("Ticket", _gh(n), source="github-issues", title=rec["title"], ticket_type=rec["ticket_type"],
                   status=rec["state"].upper(), state=rec["state"], state_reason=rec.get("state_reason"),
                   labels=rec["labels"], milestone=rec.get("milestone"), url=rec.get("url") or remote.web("issues", n),
                   created_at=rec.get("created_at"), closed_at=rec.get("closed_at"), author=rec.get("author"),
                   has_sub_issues=bool(rec.get("has_sub_issues")))
    for n, rec in sorted(issues_online.items()):
        parent = rec.get("parent")
        if parent and parent in issues_online and n not in pr_numbers:
            g.add_edge("CHILD_OF", "Ticket", _gh(n), "Ticket", _gh(parent), source="github-sub-issues", confidence=1.0,
                       evidence_ref=f"sub-issue of #{parent}")

    # ── pull requests ──
    for n in sorted(pr_numbers):
        off, on = offline.get(n), prs_online.get(n)
        props: dict = {"number": n, "url": remote.web("pull", n)}
        if off:
            props.update(title=off.title, state="merged", merged_at=off.merged_at, head=off.head, merge_style=off.merge_style,
                         merge_commit=off.merge_commit)
        if on:
            props.update(title=on["title"], state=on["state"], merged_at=on.get("merged_at") or props.get("merged_at"),
                         base=on.get("base"), head=on.get("head") or props.get("head"), labels=on["labels"],
                         url=on.get("url") or props["url"], author=on.get("author"))
            if on.get("merge_commit"):
                props["merge_commit"] = on["merge_commit"]
                if not props.get("merge_style") and on["merge_commit"] in known and len(known[on["merge_commit"]].parents) >= 2:
                    props["merge_style"] = "merge"
        g.add_node("PullRequest", _pr(n), source="github-pull-requests" if on else "git-log", **props)

        # MERGES: the API's list when it has one that is not cut short, else what the subjects said
        api: dict[str, str] = {}
        complete = False
        if on and on["state"] == "merged":
            for sha in on["commits"]:
                api[sha] = "github-pr-commits"
            if on.get("merge_commit"):
                api[on["merge_commit"]] = "github-pr-commits"
            complete = on.get("commits_total", 0) <= len(on["commits"])
        for sha, src in sorted(api.items()):
            if sha in known:
                commit_node(sha)
                g.add_edge("MERGES", "PullRequest", _pr(n), "Commit", sha, source=src, confidence=1.0,
                           evidence_ref="GitHub: the pull request's commit list and merge commit")
        if off:
            for sha, src in sorted(off.commits.items()):
                if sha in api or (on and on["state"] == "merged" and complete):
                    continue          # confirmed above, or contradicted by the complete list
                commit_node(sha)
                g.add_edge("MERGES", "PullRequest", _pr(n), "Commit", sha, source=src, confidence=OFFLINE_CONFIDENCE,
                           evidence_ref=github.public_subject(known[sha].subject, authors)[:80] if src == SQUASH_SOURCE or sha == off.merge_commit
                           else f"git rev-list {off.merge_commit[:10]}^1..{off.merge_commit[:10]}^2")

        # CLOSES: GitHub's own record replaces whatever the commit messages suggested
        if on:
            for t in on["closes"]:
                if t not in issues_online:   # closed by GitHub's record, but not in the issue listing (not read yet, or moved)
                    g.add_node("Ticket", _gh(t), source="github-closing-reference", ticket_type="ISSUE", fetched=False,
                               url=remote.web("issues", t))
                g.add_edge("CLOSES", "PullRequest", _pr(n), "Ticket", _gh(t), source="github-closing-reference", confidence=1.0,
                           evidence_ref="GitHub: closing issue reference")
        elif off:
            for t in sorted(off.closes):
                if t in pr_numbers:           # `Fixes #N` where N is a pull request, not an issue
                    continue
                verified = t in issues_online
                if not verified:
                    g.add_node("Ticket", _gh(t), source="git-closing-keyword", ticket_type="ISSUE", unverified=True,
                               url=remote.web("issues", t))
                g.add_edge("CLOSES", "PullRequest", _pr(n), "Ticket", _gh(t), source="git-closing-keyword",
                           confidence=CLOSES_OFFLINE_CONFIDENCE,
                           evidence_ref=f"closing keyword for #{t} in a commit message of the pull request",
                           extra={"unverified": not verified})

    # ── commit messages that mention an issue (online only: offline, #N might be a pull request) ──
    if issues_online:
        for c in commits:
            for n in sorted({int(x) for x in _MENTION.findall(c.subject + "\n" + c.body)}):
                if n in issues_online and n not in pr_numbers:
                    commit_node(c.sha)
                    g.add_edge("REFERENCES", "Commit", c.sha, "Ticket", _gh(n), source="git-hash-mention",
                               confidence=MENTION_CONFIDENCE, evidence_ref=f"commit message mentions #{n}")
    return g


def extract(ctx: ProjectContext, github_flag: bool | None = None, transport: github.Transport | None = None,
            since: str = DEFAULT_SINCE) -> tuple[DevKBGraph, dict | None]:
    """(the graph, a report for the manifest or None when there is no GitHub remote)."""
    cfg = github.settings(ctx.repo_root, github_flag)
    remote = github.origin_remote(ctx.repo_root, cfg.host)
    if remote is None:
        if cfg.enabled:
            print("devkb build: github layer requested but `origin` is not a GitHub remote; offline only", file=sys.stderr)
            return DevKBGraph(), {"mode": "offline", "status": "no-remote", "reason": "origin is not a GitHub remote"}
        return DevKBGraph(), None
    commits = read_log(ctx.repo_root, since)
    offline = scan(commits, ctx.repo_root)
    online: github.Online | None = None
    large = sorted(n for n, pr in offline.items() if pr.too_large)
    report: dict = {"remote": remote.slug, "mode": "offline", "status": "offline",
                    "reason": "online layer not requested", "offline_pull_requests": len(offline)}
    if cfg.enabled:
        online = github.fetch(remote, ctx.devkb_dir / "github", authors=cfg.authors, transport=transport)
        report = {**online.report, "offline_pull_requests": len(offline)}
        if report["status"] != "ok":
            print(f"devkb build: github layer {report['status']} ({report.get('reason')}); "
                  f"not fetched: {', '.join(report.get('not_fetched') or [])}; the answers use the offline layer"
                  + (" and the cache" if report.get("stale_cache_used") else ""), file=sys.stderr)
    if large:
        report["merges_not_expanded"] = large[:50]  # more than MAX_BROUGHT_IN commits: only the merge commit is linked
    return build_graph(remote, commits, offline, online if online and (online.prs or online.issues) else None,
                       cfg.authors), report
