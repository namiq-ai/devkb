"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers, one graph:

  offline   always on, git only. A `Merge pull request #N from <owner>/<branch>` commit and a squash commit whose
            subject ends `(#N)` give a PullRequest and MERGES edges (confidence 0.9: a subject is editable text). A
            closing keyword in the commit messages of such a pull request (`Fixes #N`) gives CLOSES at 0.7 to a
            Ticket `GH-N` marked `unverified`, because offline `#N` may be a pull request, not an issue.
  online    opt-in (`devkb build --github`), see devkb/github_api.py. Issues become Ticket nodes `GH-<n>`, pull
            requests gain their API record, MERGES comes from the API's commit list (1.0, also for rebase merges),
            CLOSES from GitHub's own closing references (1.0) and replaces the offline guess for every pull request
            the API was read for, and a `#N` in a commit message that is an issue gives REFERENCES (0.8).

Not stored, in either layer: descriptions, review text, e-mail addresses, and the author's login unless the
repository sets `"github": {"authors": true}`. A description is parsed for references and dropped.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from devkb.github_api import Result, origin
from devkb.model import DevKBGraph

_MERGE = re.compile(r"^Merge pull request #(\d+) from (?:([^/\s]+)/)?(\S+)")
_SQUASH = re.compile(r"^(.*\S)\s*\(#(\d+)\)$")
_CLOSING = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+#(\d+)\b")
_MENTION = re.compile(r"(?<![\w/&])#(\d+)\b")
_RS, _US = "\x1e", "\x1f"

_LABEL_TYPES = {"bug": "BUG", "epic": "EPIC", "enhancement": "FEATURE", "feature": "FEATURE"}


def _git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=300,
                              errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class PR:
    number: int
    title: str = ""
    merged_at: str = ""
    head: str | None = None
    author: str | None = None
    style: str = ""
    merges: dict[str, str] = field(default_factory=dict)       # sha -> offline source
    closes: dict[int, str] = field(default_factory=dict)       # issue number -> sha whose message carried the keyword


@dataclass
class Offline:
    prs: dict[int, PR] = field(default_factory=dict)
    messages: dict[str, str] = field(default_factory=dict)     # sha -> subject + body, for `#N` mentions (online only)
    pr_of_commit: dict[str, int] = field(default_factory=dict)


def _records(text: str) -> list[list[str]]:
    return [rec.strip("\n").split(_US) for rec in text.split(_RS) if rec.strip()]


def read_git(repo_root: Path) -> Offline:
    """One `git log` pass over HEAD, plus one `git log` per merge commit for the commits it brought in."""
    off = Offline()
    log = _records(_git(repo_root, "log", "HEAD", f"--format=%H{_US}%P{_US}%cI{_US}%s{_US}%b{_RS}"))
    for rec in log:
        if len(rec) < 4:
            continue
        sha, parents, when, subject = rec[0], rec[1].split(), rec[2], rec[3]
        body = rec[4] if len(rec) > 4 else ""
        off.messages[sha] = f"{subject}\n{body}"
        merge = _MERGE.match(subject) if len(parents) > 1 else None
        squash = _SQUASH.match(subject) if len(parents) <= 1 and not merge else None
        if merge:
            n = int(merge.group(1))
            pr = off.prs.setdefault(n, PR(n))
            pr.title = pr.title or next((ln.strip() for ln in body.splitlines() if ln.strip()), subject)
            pr.head, pr.author, pr.style = merge.group(3), merge.group(2), "merge"
            pr.merged_at = min(filter(None, [pr.merged_at, when]))
            pr.merges[sha] = "git-merge-subject"
            off.pr_of_commit[sha] = n
            for k in _CLOSING.findall(f"{subject}\n{body}"):
                pr.closes.setdefault(int(k), sha)
            for brec in _records(_git(repo_root, "log", f"--format=%H{_US}%B{_RS}", f"{parents[0]}..{parents[1]}")):
                if not brec[0].strip():
                    continue
                bsha = brec[0].strip()
                pr.merges.setdefault(bsha, "git-merge-subject")
                off.pr_of_commit.setdefault(bsha, n)
                for k in _CLOSING.findall(brec[1] if len(brec) > 1 else ""):
                    pr.closes.setdefault(int(k), bsha)
        elif squash:
            n = int(squash.group(2))
            pr = off.prs.setdefault(n, PR(n))
            pr.title = pr.title or squash.group(1).strip()
            pr.style = pr.style or "squash"
            pr.merged_at = min(filter(None, [pr.merged_at, when]))
            pr.merges.setdefault(sha, "git-squash-subject")
            off.pr_of_commit[sha] = n
            for k in _CLOSING.findall(body):
                pr.closes.setdefault(int(k), sha)
    return off


def ticket_type(row: dict) -> str:
    """The issue's own type where the repository uses issue types, else its labels, else ISSUE."""
    if row.get("issue_type"):
        return re.sub(r"\W+", "_", str(row["issue_type"]).strip()).strip("_").upper() or "ISSUE"
    for label in row.get("labels") or []:
        if label.lower() in _LABEL_TYPES:
            return _LABEL_TYPES[label.lower()]
    return "ISSUE"


def _existing(repo_root: Path, shas: set[str]) -> set[str]:
    """Which of `shas` are commits in this clone (a shallow clone lacks some of the API's)."""
    if not shas:
        return set()
    try:
        out = subprocess.run(["git", "cat-file", "--batch-check"], cwd=repo_root, input="\n".join(sorted(shas)) + "\n",
                             capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {parts[0] for parts in (ln.split() for ln in out.splitlines()) if len(parts) > 1 and parts[1] == "commit"}


def extract(repo_root: Path, online: Result | None = None, authors: bool = False, off: Offline | None = None) -> tuple[DevKBGraph, dict]:
    """The PullRequest/Ticket nodes and MERGES/CLOSES/CHILD_OF/REFERENCES edges, and a summary for the manifest."""
    g = DevKBGraph()
    off = off or read_git(repo_root)
    remote = origin(repo_root)
    url_base = f"https://{remote[0]}/{remote[1]}/{remote[2]}" if remote else ""
    issues = online.issues if online else {}
    pulls = online.pulls if online else {}
    links = online.links if online else {}

    # ── pull requests: the git record first, the API's record over it ────────────────────────────────────────
    numbers = set(off.prs) | set(pulls)
    for n in sorted(numbers):
        pr, api = off.prs.get(n), pulls.get(n)
        props = {"number": n, "state": "merged", "merged_at": pr.merged_at or None if pr else None,
                 "title": pr.title if pr else None, "head": pr.head if pr else None,
                 "merge_style": pr.style or None if pr else None,
                 "url": f"{url_base}/pull/{n}" if url_base else None}
        if authors and pr and pr.author:
            props["author"] = pr.author
        if api:
            props.update({k: api.get(k) for k in ("title", "state", "merged_at", "base", "head", "labels", "url")})
            if authors and api.get("author"):
                props["author"] = api["author"]
        link = links.get(n)
        props["merges_source"] = "github-api" if link or (api and api.get("merge_commit")) else "git-subject"
        props["closes_source"] = "github-api" if link is not None else "git-keyword"
        g.add_node("PullRequest", f"PR-{n}", source="github-api" if api else "git-merge-subject", **props)

    # ── MERGES ───────────────────────────────────────────────────────────────────────────────────────────────
    edges: dict[tuple[int, str], tuple[str, float, str]] = {}
    for n, pr in off.prs.items():
        for sha, src in pr.merges.items():
            edges[(n, sha)] = (src, 0.9, "merge commit subject" if src == "git-merge-subject" else "squash commit subject (#N)")
    if links or pulls:
        wanted = {s for n, link in links.items() for s in link.get("commits", []) + [link.get("merge_commit")] if s}
        wanted |= {p["merge_commit"] for p in pulls.values() if p.get("merge_commit")}
        local = _existing(repo_root, wanted)
        for n in sorted(numbers):
            link = links.get(n)
            shas = {s for s in (link or {}).get("commits", []) if s in local}
            for s in ((link or {}).get("merge_commit"), (pulls.get(n) or {}).get("merge_commit")):
                if s in local:
                    shas.add(s)
            complete = bool(link) and (link.get("commits_total") or 0) <= len(link.get("commits", []))
            if complete:  # the API's list is the whole list: an offline edge it does not contain is contradicted
                for key in [k for k in edges if k[0] == n and k[1] not in shas]:
                    del edges[key]
            for s in shas:
                edges[(n, s)] = ("github-api", 1.0, "GitHub pull request commit list")
    for (n, sha), (src, conf, ev) in sorted(edges.items()):
        g.add_node("Commit", sha, source="git-pr", short_hash=sha[:10])
        g.add_edge("MERGES", "PullRequest", f"PR-{n}", "Commit", sha, source=src, confidence=conf, evidence_ref=ev)

    # ── hosted issues ────────────────────────────────────────────────────────────────────────────────────────
    for n, row in sorted(issues.items()):
        props = {"title": row.get("title"), "ticket_type": ticket_type(row), "state": row.get("state"),
                 "status": row.get("state"), "state_reason": row.get("state_reason"), "labels": row.get("labels"),
                 "milestone": row.get("milestone"), "url": row.get("url"), "created_at": row.get("created_at"),
                 "closed_at": row.get("closed_at"), "has_sub_issues": True if row.get("sub_issues") else None}
        if authors and row.get("author"):
            props["author"] = row["author"]
        g.add_node("Ticket", f"GH-{n}", source="github-issues", **props)
    for n, row in sorted(issues.items()):
        if row.get("parent") in issues:
            g.add_edge("CHILD_OF", "Ticket", f"GH-{n}", "Ticket", f"GH-{row['parent']}", source="github-sub-issues",
                       confidence=1.0, evidence_ref=f"issue #{n} parent_issue_url")

    # ── CLOSES ───────────────────────────────────────────────────────────────────────────────────────────────
    unverified = 0
    for n in sorted(numbers):
        link = links.get(n)
        if link is not None:  # GitHub's own record replaces any guess from commit messages
            for m in link.get("closes", []):
                if m in issues:
                    g.add_edge("CLOSES", "PullRequest", f"PR-{n}", "Ticket", f"GH-{m}", source="github-closing-references",
                               confidence=1.0, evidence_ref=f"GitHub closingIssuesReferences of #{n}")
            continue
        for m, sha in sorted((off.prs[n].closes if n in off.prs else {}).items()):
            if m == n or m in pulls or m in off.prs:
                continue  # a pull request, not an issue
            known = m in issues
            if not known:
                g.add_node("Ticket", f"GH-{m}", source="git-closing-keyword", unverified=True)
                unverified += 1
            g.add_edge("CLOSES", "PullRequest", f"PR-{n}", "Ticket", f"GH-{m}", source="git-closing-keyword", confidence=0.7,
                       evidence_ref=f"closing keyword in commit {sha[:10]}", extra={} if known else {"unverified": True})

    # ── REFERENCES: a `#N` in a commit message, only where the API says N is an issue ─────────────────────────
    refs = 0
    if issues:
        for sha, text in off.messages.items():
            own = off.pr_of_commit.get(sha)
            for m in sorted({int(x) for x in _MENTION.findall(text)}):
                if m in issues and m != own:
                    g.add_node("Commit", sha, source="git-pr", short_hash=sha[:10])
                    g.add_edge("REFERENCES", "Commit", sha, "Ticket", f"GH-{m}", source="git-hash-mention", confidence=0.8,
                               evidence_ref=f"#{m} in commit message")
                    refs += 1
    summary = {"offline_pull_requests": len(off.prs), "pull_requests": len(numbers), "issues": len(issues),
               "merges_edges": len(edges), "closes_unverified": unverified, "hash_mentions": refs}
    return g, summary
