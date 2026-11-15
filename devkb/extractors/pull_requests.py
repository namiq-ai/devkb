"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers over the same nodes:

  offline (always on, git alone)   a `Merge pull request #N from o/b` merge commit or a squash commit whose subject ends
                                   `(#N)` gives PullRequest PR-N and MERGES (0.9: a subject is text a person can edit);
                                   a closing keyword in a commit message of that pull request gives CLOSES at 0.7 to an
                                   `unverified` Ticket GH-N, because offline `#N` may be a pull request, not an issue.
                                   A repository without a hosting remote gets nothing: `(#12)` there is not a pull request.
  online (opt in, devkb/github.py)  the API's pull requests, commit lists, closing references, issues and sub-issues.
                                   Replaces what it can confirm, removes what it contradicts, and where it could not
                                   fetch something says so in the returned status.

Not stored anywhere: descriptions, review text, and logins unless the repository set `github.authors`.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from devkb import github as gh
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext, github_config

MAX_BROUGHT_IN = 1000          # commits one merge may bring in before it is judged not to be a pull request branch
_MERGE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?[ \t]+((?:[\w.-]+/[\w.-]+)?)#(\d+)", re.IGNORECASE)
_MENTION = re.compile(r"(?<![\w&/#])#(\d+)\b")

SRC_MERGE, SRC_SQUASH, SRC_KEYWORD = "git-merge-subject", "git-squash-subject", "git-closing-keyword"
SRC_API_COMMITS, SRC_API_MERGE_COMMIT, SRC_API_CLOSES = "github-pr-commits", "github-pr-merge-commit", "github-closing-references"
SRC_MENTION, SRC_SUB_ISSUES = "git-hash-mention", "github-sub-issues"


@dataclass
class _Commit:
    sha: str
    parents: list[str]
    committed: str
    date: str
    author: str
    subject: str
    body: str

    @property
    def message(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class _PR:
    number: int
    title: str = ""
    style: str | None = None
    head: str | None = None
    merged_at: str | None = None
    links: dict[str, tuple[str, float]] = field(default_factory=dict)    # commit sha -> (source, confidence)
    message_shas: list[str] = field(default_factory=list)


def _git(args: list[str], cwd: Path, timeout: int = 300) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                              errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read_commits(repo_root: Path) -> dict[str, _Commit]:
    fmt = "%x1e%H%x1f%P%x1f%cI%x1f%ad%x1f%an%x1f%s%x1f%b"
    out = _git(["log", "--all", f"--format={fmt}", "--date=short"], repo_root)
    commits: dict[str, _Commit] = {}
    for rec in out.split("\x1e"):
        f = rec.split("\x1f", 6)
        if len(f) == 7 and f[0].strip():
            sha = f[0].strip()
            commits[sha] = _Commit(sha, f[1].split(), f[2], f[3], f[4], f[5], f[6])
    return commits


def _node_commit(g: DevKBGraph, c: _Commit) -> None:
    g.add_node("Commit", c.sha, source="git-log-baseline", short_hash=c.sha[:10], date=c.date, author=c.author, subject=c.subject)


def _closing_numbers(text: str, slug: str) -> list[int]:
    found = []
    for repo, num in _CLOSING.findall(text):
        if repo and repo.lower() != slug.lower():
            continue                                                  # another repository's issue
        found.append(int(num))
    return found


def parse_offline(commits: dict[str, _Commit], repo_root: Path) -> dict[int, _PR]:
    prs: dict[int, _PR] = {}
    for c in commits.values():
        m = _MERGE.match(c.subject)
        if m and len(c.parents) >= 2:
            pr = prs.setdefault(int(m[1]), _PR(int(m[1])))
            pr.style, pr.merged_at = "merge", c.committed
            pr.head = m[2].split("/", 1)[-1]
            pr.title = next((ln.strip() for ln in c.body.splitlines() if ln.strip()), "") or pr.title
            pr.links[c.sha] = (SRC_MERGE, 0.9)
            pr.message_shas.append(c.sha)
            brought = _git(["rev-list", f"{c.sha}^1..{c.sha}^2"], repo_root).split()
            if len(brought) > MAX_BROUGHT_IN:
                brought = []
            for b in brought:
                pr.links.setdefault(b, (SRC_MERGE, 0.9))
                pr.message_shas.append(b)
            continue
        m = _SQUASH.search(c.subject)
        if m and len(c.parents) == 1:
            pr = prs.setdefault(int(m[1]), _PR(int(m[1])))
            pr.style = pr.style or "squash"
            pr.merged_at = pr.merged_at or c.committed
            pr.title = pr.title or _SQUASH.sub("", c.subject).strip()
            pr.links[c.sha] = (SRC_SQUASH, 0.9)
            pr.message_shas.append(c.sha)
    return prs


# ── hosted issues → Ticket fields ────────────────────────────────────────────────────────────────────────
_TYPE_BY_NAME = {"bug": "BUG", "epic": "EPIC", "enhancement": "FEATURE", "feature": "FEATURE", "task": "TASK"}


def ticket_type_of(issue: dict) -> str:
    """The issue's own type where the repository uses issue types, else its labels, else ISSUE."""
    t = (issue.get("type") or "").strip().lower()
    if t:
        return _TYPE_BY_NAME.get(t, t.upper())
    for label in issue.get("labels") or []:
        name = label.lower().removeprefix("type:").removeprefix("type/").strip()
        if name in _TYPE_BY_NAME:
            return _TYPE_BY_NAME[name]
    return "ISSUE"


def _issue_props(issue: dict) -> dict:
    props = {"title": issue["title"], "state": issue["state"], "status": (issue["state"] or "").upper(),
             "state_reason": issue.get("state_reason"), "labels": issue.get("labels") or [],
             "milestone": issue.get("milestone"), "url": issue.get("url"), "created_at": issue.get("created_at"),
             "closed_at": issue.get("closed_at"), "ticket_type": ticket_type_of(issue)}
    if issue.get("sub_issues") or issue.get("n_sub_issues"):
        props["has_sub_issues"] = True
    if issue.get("author"):
        props["author"] = issue["author"]
    return props


def _pr_url(remote: gh.Remote | None, n: int) -> str | None:
    return f"{remote.web}/pull/{n}" if remote else None


def _infer_style(pull: dict, commits: dict[str, _Commit]) -> str | None:
    """merge / squash / rebase from the pull request's merge commit, when git can tell."""
    mc = commits.get(pull.get("merge_commit_sha") or "")
    if mc is None or not pull.get("merged_at"):
        return None
    if len(mc.parents) >= 2:
        return "merge"
    if _SQUASH.search(mc.subject):
        return "squash"
    listed = pull.get("commits") or []
    if len(listed) > 1 and listed[-1]["subject"] == mc.subject and listed[-1]["sha"] != mc.sha:
        return "rebase"
    return None


# ── the extractor ────────────────────────────────────────────────────────────────────────────────────────
def extract(ctx: ProjectContext, github_on: bool | None = None, client: gh.Client | None = None) -> tuple[DevKBGraph, dict]:
    """The pull-request graph and a status dict for the manifest (what each layer did and could not do)."""
    g = DevKBGraph()
    cfg = github_config(ctx.repo_root)
    enabled = cfg["enabled"] if github_on is None else bool(github_on)
    remote = gh.origin_remote(ctx.repo_root)
    status: dict = {"offline": remote is not None, "remote": remote.slug if remote else None, "online": None,
                    "online_requested": enabled}
    if remote is None:
        if enabled:
            status["online"] = {"enabled": True, "complete": False, "notes": ["no hosting remote to read from"]}
        return g, status

    commits = read_commits(ctx.repo_root)
    prs = parse_offline(commits, ctx.repo_root)

    # offline CLOSES: (pr, issue number) -> evidence
    closing: dict[tuple[int, int], str] = {}
    for n, pr in prs.items():
        for sha in dict.fromkeys(pr.message_shas):
            c = commits.get(sha)
            if not c:
                continue
            for target in _closing_numbers(c.message, remote.slug):
                if target != n:
                    closing.setdefault((n, target), f"git log -1 {sha[:10]}")

    fetched = None
    if enabled:
        client = client or gh.make_client(ctx.repo_root, remote)
        if client is None:
            status["online"] = {"enabled": True, "complete": False, "notes": ["no hosting remote to read from"]}
        else:
            fetched = gh.fetch(client, ctx.devkb_dir / "github", cfg["authors"])
            status["online"] = fetched.status.to_dict()

    # ── reconcile ──
    pr_props: dict[int, dict] = {}
    merges: dict[tuple[int, str], tuple[str, float, str]] = {}       # (pr, sha) -> (source, confidence, evidence)
    for n, pr in prs.items():
        pr_props[n] = {"number": n, "title": pr.title, "state": "merged", "merged_at": pr.merged_at, "head": pr.head,
                       "merge_style": pr.style, "url": _pr_url(remote, n)}
        for sha, (src, conf) in pr.links.items():
            merges[(n, sha)] = (src, conf, f"git show -s {sha[:10]}")

    tickets: dict[int, dict] = {}                                      # GH-n -> properties (+ "unverified")
    closes: dict[tuple[int, int], tuple[str, float, bool, str]] = {}   # (pr, issue) -> source, conf, unverified, evidence
    for (n, t), ev in closing.items():
        closes[(n, t)] = (SRC_KEYWORD, 0.7, True, ev)
        tickets.setdefault(t, {"unverified": True})
    child_of: list[tuple[int, int]] = []
    mentioned: dict[str, set[int]] = {}

    if fetched is not None:
        st = fetched.status
        for n, issue in fetched.issues.items():
            tickets[n] = _issue_props(issue)
            if issue.get("parent"):
                child_of.append((n, issue["parent"]))
            child_of += [(s, n) for s in issue.get("sub_issues") or []]
        if st.issues_complete:
            for t in [t for t, p in tickets.items() if p.get("unverified")]:
                if t not in fetched.issues:                              # a pull request, or not an issue of this repository
                    del tickets[t]
                    for key in [k for k in closes if k[1] == t and closes[k][2]]:
                        del closes[key]
        for n, pull in fetched.pulls.items():
            props = pr_props.setdefault(n, {"number": n})
            style = props.get("merge_style") or _infer_style(pull, commits)
            props.update({k: pull.get(k) for k in ("title", "state", "merged_at", "base", "head", "labels", "url")
                          if pull.get(k) is not None})
            if style:
                props["merge_style"] = style
            if pull.get("author"):
                props["author"] = pull["author"]
            for c in pull.get("commits") or []:
                if c["sha"] in commits:
                    merges[(n, c["sha"])] = (SRC_API_COMMITS, 1.0, f"GET pulls/{n}/commits")
            if pull.get("merge_commit_sha") in commits:
                merges[(n, pull["merge_commit_sha"])] = (SRC_API_MERGE_COMMIT, 1.0, f"GET pulls/{n}")
            for key in [k for k in closes if k[0] == n]:                 # GitHub's record replaces and corrects the guess
                del closes[key]
            for t in pull.get("closes") or []:
                closes[(n, t)] = (SRC_API_CLOSES, 1.0, False, f"GraphQL closingIssuesReferences of #{n}")
                tickets.setdefault(t, {})
        # a mention of #N in a commit that is an issue: Commit -> Ticket
        issue_numbers = set(fetched.issues)
        for sha, c in commits.items():
            nums = {int(x) for x in _MENTION.findall(c.message)} & issue_numbers
            if nums:
                mentioned[sha] = nums

    # ── emit ──
    for n, props in pr_props.items():
        g.add_node("PullRequest", f"PR-{n}", source="git" if n in prs else "github", **props)
    for t, props in tickets.items():
        props = dict(props)
        g.add_node("Ticket", f"GH-{t}", source="git" if props.get("unverified") else "github-issues", **props)
    for (n, sha), (src, conf, ev) in merges.items():
        _node_commit(g, commits[sha])
        g.add_edge("MERGES", "PullRequest", f"PR-{n}", "Commit", sha, source=src, confidence=conf, evidence_ref=ev)
    for (n, t), (src, conf, unverified, ev) in closes.items():
        g.add_edge("CLOSES", "PullRequest", f"PR-{n}", "Ticket", f"GH-{t}", source=src, confidence=conf, evidence_ref=ev,
                   extra={"unverified": True} if unverified else None)
    for child, parent in sorted(set(child_of)):
        for t in (child, parent):
            if t not in tickets:
                g.add_node("Ticket", f"GH-{t}", source="github-issues")
        g.add_edge("CHILD_OF", "Ticket", f"GH-{child}", "Ticket", f"GH-{parent}", source=SRC_SUB_ISSUES, confidence=1.0,
                   evidence_ref=f"GET issues/{parent}/sub_issues")
    for sha, nums in mentioned.items():
        _node_commit(g, commits[sha])
        for t in sorted(nums):
            g.add_edge("REFERENCES", "Commit", sha, "Ticket", f"GH-{t}", source=SRC_MENTION, confidence=0.8,
                       evidence_ref=f"git show -s {sha[:10]}")

    status.update({"n_pull_requests": len(pr_props), "n_unverified_closes": sum(1 for v in closes.values() if v[2]),
                   "n_closes": len(closes)})
    return g, status
