"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers, both producing the same nodes and verbs:

  offline (always)   from git alone, one `git log` pass:
                       `Merge pull request #N from o/branch`  -> PullRequest PR-N, MERGES to the merge commit and the
                                                                 commits it brought in (`rev-list M^1..M^2`)
                       `<subject> (#N)` on one parent          -> PullRequest PR-N, MERGES to the squash commit
                       `Fixes|Closes|Resolves #N` in those commits' messages -> CLOSES PR-N -> GH-N, unverified
                     MERGES: confidence 0.9 (a subject is text a person can edit). CLOSES: 0.7, and the target
                     Ticket is marked `unverified: true`, because offline `#N` may be a pull request, not an issue.
  online (opt-in)    devkb/github_api.py's fetch: pull requests (commit list, GitHub's own closing record) and
                     issues. It is authoritative for every pull request it covers: MERGES and CLOSES come from the
                     API at 1.0, the offline edges for that pull request are dropped (an offline link the API does
                     not confirm is a link GitHub contradicts), and a bare `#N` in a commit message that resolves to
                     an issue gives REFERENCES Commit -> GH-N at 0.8.

Never stored: descriptions, review text, comments. The author's login only when the fetch was asked for it.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from devkb.extractors.source_baseline import DEFAULT_SINCE
from devkb.github_api import Fetch, Remote, origin_remote
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from (\S+)")
SQUASH_SUBJECT = re.compile(r"^(.*\S)\s+\(#(\d+)\)\s*$")
_CLOSE_KEYWORD = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?[ \t]+((?:#\d+)(?:[ \t]*(?:,|and|&)[ \t]*#\d+)*)",
                            re.IGNORECASE)
_MENTION = re.compile(r"(?<![\w/#&])#(\d+)\b")
_NUMBERS = re.compile(r"#(\d+)")
MERGES_CONFIDENCE, CLOSES_OFFLINE_CONFIDENCE, MENTION_CONFIDENCE = 0.9, 0.7, 0.8
MAX_BROUGHT_IN = 2000


@dataclass
class CommitRec:
    sha: str
    parents: list[str]
    date: str
    subject: str
    body: str

    @property
    def message(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class OfflinePR:
    number: int
    style: str
    title: str
    merged_at: str
    head: str | None
    commits: list[str] = field(default_factory=list)       # in order; the merge/squash commit first
    messages: list[str] = field(default_factory=list)


def read_history(repo_root: Path, since: str = DEFAULT_SINCE) -> dict[str, CommitRec]:
    try:
        out = subprocess.run(["git", "log", "--all", f"--since={since}", "--format=%x1e%H%x1f%P%x1f%cI%x1f%B"],
                             cwd=repo_root, capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    recs: dict[str, CommitRec] = {}
    for chunk in out.split("\x1e"):
        parts = chunk.strip("\n").split("\x1f", 3)
        if len(parts) != 4 or not parts[0]:
            continue
        subject, _, body = parts[3].partition("\n")
        recs[parts[0].strip()] = CommitRec(parts[0].strip(), parts[1].split(), parts[2], subject.strip(), body.strip())
    return recs


def _brought_in(repo_root: Path, merge: CommitRec) -> list[str]:
    try:
        out = subprocess.run(["git", "rev-list", f"--max-count={MAX_BROUGHT_IN}", f"{merge.parents[0]}..{merge.parents[1]}"],
                             cwd=repo_root, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return out.split()


def offline_pull_requests(repo_root: Path, recs: dict[str, CommitRec]) -> dict[int, OfflinePR]:
    found: dict[int, OfflinePR] = {}
    for rec in recs.values():
        if len(rec.parents) == 2 and (m := MERGE_SUBJECT.match(rec.subject)):
            number = int(m.group(1))
            title = next((ln.strip() for ln in rec.body.splitlines() if ln.strip()), "") or rec.subject
            brought = _brought_in(repo_root, rec)
            pr = OfflinePR(number, "merge", title, rec.date, m.group(2).split("/", 1)[-1],
                           [rec.sha] + brought, [rec.message] + [recs[s].message for s in brought if s in recs])
        elif len(rec.parents) == 1 and (m := SQUASH_SUBJECT.match(rec.subject)):
            pr = OfflinePR(int(m.group(2)), "squash", m.group(1), rec.date, None, [rec.sha], [rec.message])
        else:
            continue
        old = found.get(pr.number)
        if old is None:
            found[pr.number] = pr
        else:       # a backport or a re-merge: keep every commit, and the merge-commit reading when there is one
            old.commits += [c for c in pr.commits if c not in old.commits]
            old.messages += pr.messages
            if pr.style == "merge" and old.style != "merge":
                old.style, old.title, old.head = pr.style, pr.title, pr.head
    return found


def closing_numbers(messages: list[str], own: int) -> list[int]:
    out: dict[int, None] = {}
    for msg in messages:
        for m in _CLOSE_KEYWORD.finditer(msg):
            for n in _NUMBERS.findall(m.group(1)):
                if int(n) != own:
                    out[int(n)] = None
    return list(out)


def pr_url(remote: Remote | None, number: int) -> str | None:
    return f"{remote.web}/pull/{number}" if remote and remote.host == "github.com" else None


def extract(ctx: ProjectContext, graph: DevKBGraph, fetch: Fetch | None = None, since: str = DEFAULT_SINCE) -> tuple[DevKBGraph, dict]:
    """New PullRequest/Ticket nodes and MERGES/CLOSES/CHILD_OF/REFERENCES edges for `graph`'s commits.
    Returns (graph of additions, statistics for the manifest)."""
    g = DevKBGraph()
    fetch = fetch or Fetch()
    remote = fetch.remote or origin_remote(ctx.repo_root)
    stats = {"offline_pull_requests": 0, "unverified_closes": 0, "api_commits_not_in_graph": 0, "dropped_offline": 0}
    if remote is None:       # a repository without a hosting remote gets no new nodes
        return g, stats
    recs = read_history(ctx.repo_root, since)
    offline = offline_pull_requests(ctx.repo_root, recs)
    known_commits = {n.natural_key for n in graph.nodes("Commit")}
    api = fetch.prs
    authoritative = fetch.requested and fetch.prs_complete

    # An offline pull request the API (listing complete) does not know, or that is an issue there, was a subject ending "(#N)"
    # for an issue: GitHub numbers issues and pull requests from one sequence.
    for n in [n for n in offline if (authoritative and n not in api) or n in fetch.issues]:
        del offline[n]
        stats["dropped_offline"] += 1
    stats["offline_pull_requests"] = len(offline)
    pr_numbers = set(offline) | set(api)
    issue_numbers = set(fetch.issues)

    def ticket_exists(number: int) -> bool:
        return number in issue_numbers

    # ── hosted issues ──
    for n, iss in sorted(fetch.issues.items()):
        ttype = iss["ticket_type"]
        if ttype == "ISSUE" and iss.get("sub_issues"):
            ttype = "EPIC"
        g.add_node("Ticket", f"GH-{n}", source="github-issues", title=iss["title"], state=iss["state"],
                   status=iss["state"].upper(), state_reason=iss.get("state_reason"), labels=iss["labels"],
                   milestone=iss.get("milestone"), url=iss.get("url"), created_at=iss.get("created_at"),
                   closed_at=iss.get("closed_at"), ticket_type=ttype, author=iss.get("author"))
        parent = iss.get("parent")
        same_repo = not iss.get("parent_repo") or iss["parent_repo"].lower() == remote.slug.lower()
        if parent and same_repo and ticket_exists(int(parent)):
            g.add_edge("CHILD_OF", "Ticket", f"GH-{n}", "Ticket", f"GH-{parent}", source="github-sub-issues",
                       confidence=1.0, evidence_ref=f"sub-issue of #{parent}")

    # ── pull requests ──
    def commit_edge(number: int, sha: str, source: str, confidence: float, evidence: str) -> bool:
        if sha not in known_commits:
            return False
        g.add_edge("MERGES", "PullRequest", f"PR-{number}", "Commit", sha, source=source, confidence=confidence,
                   evidence_ref=evidence)
        return True

    for number in sorted(pr_numbers):
        off, rec = offline.get(number), api.get(number)
        key = f"PR-{number}"
        style = off.style if off else None
        if rec is not None:
            mc = recs.get(rec.get("merge_commit") or "")
            if style is None and mc is not None and len(mc.parents) == 2:
                style = "merge"
            g.add_node("PullRequest", key, source="github-pull-requests", number=number, title=rec["title"],
                       state=rec["state"], merged_at=rec.get("merged_at"), base=rec.get("base"), head=rec.get("head"),
                       labels=rec["labels"], url=rec.get("url"), merge_style=style, author=rec.get("author"))
            shas = list(dict.fromkeys(([rec["merge_commit"]] if rec.get("merge_commit") and rec["state"] == "merged" else [])
                                      + (rec["commits"] if rec["state"] == "merged" else [])))
            for sha in shas:
                if not commit_edge(number, sha, "github-pr-commits", 1.0, f"GitHub: commits of pull request #{number}"):
                    stats["api_commits_not_in_graph"] += 1
            for n in rec["closes"]:
                if not ticket_exists(n):       # confirmed by GitHub, but the issue itself was not fetched
                    g.add_node("Ticket", f"GH-{n}", source="github-issues", url=(f"{remote.web}/issues/{n}"))
                g.add_edge("CLOSES", "PullRequest", key, "Ticket", f"GH-{n}", source="github-closing-issues-references",
                           confidence=1.0, evidence_ref=f"GitHub: issues pull request #{number} closes")
            continue

        assert off is not None
        source = "git-merge-subject" if off.style == "merge" else "git-squash-subject"
        g.add_node("PullRequest", key, source=source, number=number, title=off.title, state="merged",
                   merged_at=off.merged_at, head=off.head, url=pr_url(remote, number), merge_style=off.style)
        for sha in off.commits:
            commit_edge(number, sha, source, MERGES_CONFIDENCE,
                        f"{'Merge pull request' if off.style == 'merge' else 'subject ends'} #{number}")
        for n in closing_numbers(off.messages, number):
            if n in pr_numbers:                 # `Fixes #N` where N is itself a pull request
                continue
            if not ticket_exists(n):
                g.add_node("Ticket", f"GH-{n}", source="git-closing-keyword", unverified=True)
            g.add_edge("CLOSES", "PullRequest", key, "Ticket", f"GH-{n}", source="git-closing-keyword",
                       confidence=CLOSES_OFFLINE_CONFIDENCE, evidence_ref=f"closing keyword for #{n} in a commit of #{number}",
                       extra={"unverified": not ticket_exists(n)})
            stats["unverified_closes"] += 0 if ticket_exists(n) else 1

    # ── commit messages that mention an issue (needs the online layer to tell issues from pull requests) ──
    if issue_numbers:
        for sha, rec in recs.items():
            if sha not in known_commits:
                continue
            for n in {int(x) for x in _MENTION.findall(rec.message)}:
                if n in issue_numbers and n not in pr_numbers:
                    g.add_edge("REFERENCES", "Commit", sha, "Ticket", f"GH-{n}", source="git-hash-mention",
                               confidence=MENTION_CONFIDENCE, evidence_ref=f"commit message mentions #{n}")
    return g, stats
