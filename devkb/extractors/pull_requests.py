"""Pull requests and hosted issues (ADR-DEVKB-007).

Two layers, one result:

  offline  always on, from git alone. A merge commit `Merge pull request #N from owner/branch` and a squash commit
           whose subject ends `(#N)` name their pull request: PullRequest node, MERGES to the commit(s) it brought in
           (confidence 0.9: a subject is text a person can edit). A closing keyword (`Fixes #N`) in a pull request's
           commit messages gives CLOSES to Ticket GH-N at confidence 0.7, marked `unverified`: offline, #N might be a
           pull request. A bare `#N` gives nothing.
  online   opt-in (`devkb build --github`), read from the local cache of devkb.github. Replaces what the offline layer
           guessed with GitHub's record (MERGES from the pull request's commit list, CLOSES from its closing
           references, both confidence 1.0), adds pull requests git cannot see (open, closed, rebase-merged), hosted
           issues as Ticket nodes, sub-issue CHILD_OF, and REFERENCES from commits that mention an issue.

Not stored in either layer: descriptions, review text, and (unless `authors` is on) the author's login.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from devkb import github
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext, load_config

DEFAULT_SINCE = "3 years ago"  # the window source_baseline uses for Commit nodes; a link to a commit outside it has no end
MAX_BROUGHT_IN = 500           # commits followed from one merge commit

_MERGE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?[ \t]+"
                      r"((?:[\w.-]+/[\w.-]+)?#\d+(?:[ \t]*(?:,|and|&)[ \t]*(?:[\w.-]+/[\w.-]+)?#\d+)*)", re.IGNORECASE)
_REF = re.compile(r"([\w.-]+/[\w.-]+)?#(\d+)")
_MENTION = re.compile(r"(?<![\w/&#])#(\d+)\b")

_TYPE_BY_NAME = {"bug": "BUG", "epic": "EPIC", "enhancement": "FEATURE", "feature": "FEATURE"}


def pr_key(n: int) -> str:
    return f"PR-{n}"


def issue_key(n: int) -> str:
    return f"GH-{n}"


@dataclass
class _Pr:
    number: int
    style: str                       # merge | squash | (online only: "")
    hashes: list[str] = field(default_factory=list)   # the merge/squash commit first, then the commits a merge brought in
    title: str = ""
    head: str | None = None
    merged_at: str | None = None
    closes: set[int] = field(default_factory=set)


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _closing_numbers(text: str, own: int, slug: str) -> set[int]:
    found: set[int] = set()
    for m in _CLOSING.finditer(text):
        for ref in _REF.finditer(m.group(1)):
            repo_part, n = ref.group(1), int(ref.group(2))
            if repo_part and repo_part.lower() != slug.lower():
                continue  # another repository's issue
            if n != own:
                found.add(n)
    return found


def _read_log(repo: Path, since: str) -> dict[str, dict]:
    out = _git(repo, "log", "--all", f"--since={since}", "--format=%H%x1f%P%x1f%cI%x1f%s%x1f%b%x1e")
    commits: dict[str, dict] = {}
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) != 5 or not parts[0]:
            continue
        h, parents, cdate, subject, body = parts
        commits[h] = {"parents": parents.split(), "cdate": cdate, "subject": subject, "body": body}
    return commits


def _offline(ctx: ProjectContext, since: str, slug: str) -> tuple[dict[str, dict], dict[int, _Pr], dict[str, set[int]]]:
    commits = _read_log(ctx.repo_root, since)
    merges: dict[int, list[str]] = {}
    squashes: dict[int, list[str]] = {}
    mentions: dict[str, set[int]] = {}
    for h, c in commits.items():
        text = f"{c['subject']}\n{c['body']}"
        found = {int(n) for n in _MENTION.findall(text)}
        if found:
            mentions[h] = found
        m = _MERGE.match(c["subject"])
        if m and len(c["parents"]) >= 2:
            merges.setdefault(int(m.group(1)), []).append(h)
            continue
        s = _SQUASH.search(c["subject"])
        if s and len(c["parents"]) <= 1:
            squashes.setdefault(int(s.group(1)), []).append(h)
    prs: dict[int, _Pr] = {}
    for n, hashes in merges.items():
        pr = prs[n] = _Pr(n, "merge")
        text_parts = []
        for h in sorted(hashes, key=lambda x: commits[x]["cdate"]):
            c = commits[h]
            m = _MERGE.match(c["subject"])
            pr.hashes.append(h)
            pr.head = pr.head or (m.group(2).split("/", 1)[1] if "/" in m.group(2) else m.group(2))
            pr.merged_at = pr.merged_at or c["cdate"]
            pr.title = pr.title or next((ln.strip() for ln in c["body"].splitlines() if ln.strip()), "")
            text_parts.append(c["body"])
            brought = _git(ctx.repo_root, "rev-list", f"--max-count={MAX_BROUGHT_IN}", f"{h}^1..{h}^2").split()
            for b in brought:
                if b in commits and b not in pr.hashes:
                    pr.hashes.append(b)
                    text_parts.append(f"{commits[b]['subject']}\n{commits[b]['body']}")
        pr.closes = _closing_numbers("\n".join(text_parts), n, slug)
    for n, hashes in squashes.items():
        if n in prs:
            continue  # a merge commit names it already; a later "(#N)" is a backport or revert of it
        h = min(hashes, key=lambda x: commits[x]["cdate"])  # backports of the same change carry the same number
        c = commits[h]
        prs[n] = _Pr(n, "squash", [h], _SQUASH.sub("", c["subject"]).strip(), None, c["cdate"],
                     _closing_numbers(f"{c['subject']}\n{c['body']}", n, slug))
    return commits, prs, mentions


def _ticket_type(issue: dict) -> str:
    kind = (issue.get("type") or "").strip().lower()
    if kind:
        return _TYPE_BY_NAME.get(kind, kind.upper())
    for label in issue.get("labels") or []:
        if label.lower() in _TYPE_BY_NAME:
            return _TYPE_BY_NAME[label.lower()]
    return "ISSUE"


def extract(ctx: ProjectContext, gh: github.Options | None = None, since: str = DEFAULT_SINCE) -> tuple[DevKBGraph, dict]:
    """The graph of pull requests and hosted issues, and the report of the online layer (for the manifest)."""
    gh = gh if gh is not None else github.options(load_config(ctx.repo_root))
    remote = github.origin_remote(ctx.repo_root)
    slug = f"{remote[1]}/{remote[2]}" if remote else ""
    web = f"https://{remote[0]}/{remote[1]}/{remote[2]}" if remote else ""
    commits, prs, mentions = _offline(ctx, since, slug)

    # edge candidates: (pr, commit) -> (source, confidence, evidence); (pr, issue) -> (source, confidence, unverified, evidence)
    merges: dict[tuple[int, str], tuple[str, float, str]] = {}
    for n, pr in prs.items():
        src = "git-merge-subject" if pr.style == "merge" else "git-squash-subject"
        for h in pr.hashes:
            merges[(n, h)] = (src, 0.9, f"commit {h[:10]} subject names #{n}")
    closes: dict[tuple[int, int], tuple[str, float, bool, str]] = {}
    for n, pr in prs.items():
        for t in pr.closes:
            closes[(n, t)] = ("git-closing-keyword", 0.7, True, f"a closing keyword for #{t} in the commit messages of #{n}")

    nodes: dict[int, dict] = {n: {"state": "merged", "merged_at": p.merged_at, "title": p.title, "head": p.head,
                                  "merge_style": p.style, "url": f"{web}/pull/{n}" if web else None,
                                  "source": "git-merge-subject" if p.style == "merge" else "git-squash-subject"}
                              for n, p in prs.items()}
    issues: dict[int, dict] = {}
    report: dict = {"enabled": False}
    references: dict[tuple[str, int], str] = {}

    if gh.enabled:
        cache, rep = github.sync(ctx.repo_root, ctx.devkb_dir / "github", gh.authors)
        report = rep.to_dict()
        if cache is not None:
            issues = {int(k): v for k, v in cache["issues"].items()}
            online_prs = {int(k): v for k, v in cache["prs"].items()}
            removed = {"merges": 0, "closes": 0}
            for n, p in online_prs.items():
                merged = bool(p.get("merged_at"))
                node = nodes.setdefault(n, {"source": "github-pulls"})
                node.update({k: v for k, v in {
                    "state": "merged" if merged else ("open" if p.get("state") == "open" else "closed"),
                    "merged_at": p.get("merged_at"), "title": p.get("title"), "base": p.get("base"),
                    "head": p.get("head"), "labels": p.get("labels"), "url": p.get("url"), "author": p.get("author"),
                }.items() if v})
                node.setdefault("labels", [])
                got = cache["commits"].get(str(n))
                if merged and got is not None:
                    api = {s for s in got["shas"] + ([p["merge_commit_sha"]] if p.get("merge_commit_sha") else []) if s in commits}
                    for key in [k for k in merges if k[0] == n and k[1] not in api]:
                        del merges[key]  # the API contradicts it
                        removed["merges"] += 1
                    for h in api:
                        merges[(n, h)] = ("github-pr-commits", 1.0, f"GitHub lists commit {h[:10]} for #{n}")
                if str(n) in cache["closes"]:
                    theirs = set(cache["closes"][str(n)])
                    for key in [k for k in closes if k[0] == n and k[1] not in theirs and closes[k][1] < 1.0]:
                        del closes[key]
                        removed["closes"] += 1
                    for t in theirs:
                        closes[(n, t)] = ("github-closing-references", 1.0, False, f"GitHub records #{n} as closing #{t}")
            # an offline "closes #N" whose N is a pull request is not an issue link at all; one whose N is a known
            # issue is no longer unverified (still 0.7: GitHub's own record for this pull request was not fetched)
            for key in list(closes):
                src, conf, unverified, ev = closes[key]
                if key[1] in online_prs and key[1] not in issues:
                    del closes[key]
                    removed["closes"] += 1
                elif unverified and key[1] in issues:
                    closes[key] = (src, conf, False, ev)
            for (h, nums) in mentions.items():
                for m in nums:
                    if m in issues:
                        references[(h, m)] = f"commit {h[:10]} mentions #{m}"
            report["removed_offline_links"] = removed

    g = DevKBGraph()
    for n, node in sorted(nodes.items()):
        props = {k: v for k, v in node.items() if k != "source"}
        g.add_node("PullRequest", pr_key(n), node["source"], number=n, **props)
    for (n, h), (src, conf, ev) in sorted(merges.items()):
        g.add_node("Commit", h, "git", short_hash=h[:10], subject=commits[h]["subject"])
        g.add_edge("MERGES", "PullRequest", pr_key(n), "Commit", h, src, conf, ev)
    wanted: set[int] = {t for (_n, t) in closes}
    for n, i in sorted(issues.items()):
        wanted.add(n)
    for n in sorted(wanted):
        i = issues.get(n)
        if i is None:
            g.add_node("Ticket", issue_key(n), "git-closing-keyword", number=n, unverified=True)
            continue
        epic = bool(i.get("sub_issues"))
        g.add_node("Ticket", issue_key(n), "github-issues", number=n, title=i.get("title"), ticket_type=_ticket_type(i),
                   status=(i.get("state") or "").upper(), state=i.get("state"), state_reason=i.get("state_reason"),
                   labels=i.get("labels"), milestone=i.get("milestone"), url=i.get("url"),
                   created_at=i.get("created_at"), closed_at=i.get("closed_at"), author=i.get("author"),
                   epic=True if epic else None, unverified=False)
    for (n, t), (src, conf, unverified, ev) in sorted(closes.items()):
        g.add_edge("CLOSES", "PullRequest", pr_key(n), "Ticket", issue_key(t), src, conf, ev,
                   {"unverified": True} if unverified else {})
    for n, i in sorted(issues.items()):
        if i.get("parent") and i["parent"] in issues:
            g.add_edge("CHILD_OF", "Ticket", issue_key(n), "Ticket", issue_key(i["parent"]), "github-sub-issues", 1.0,
                       f"GitHub lists #{n} as a sub-issue of #{i['parent']}")
    for (h, m), ev in sorted(references.items()):
        g.add_edge("REFERENCES", "Commit", h, "Ticket", issue_key(m), "git-hash-mention", 0.8, ev)
    report["offline"] = {"pull_requests": len(prs), "merges": sum(1 for p in prs.values() if p.style == "merge"),
                         "squashes": sum(1 for p in prs.values() if p.style == "squash"),
                         "unverified_closes": sum(1 for v in closes.values() if v[2])}
    return g, report
