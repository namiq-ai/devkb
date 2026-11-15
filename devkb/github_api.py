"""The opt-in online layer for pull requests and hosted issues (ADR-DEVKB-007 §6).

Nothing here runs unless the build was asked for it (`devkb build --github`, or `{"github": {"enabled": true}}` in
devkb.json). A build never touches the network otherwise.

What it does when asked:
  * reads the host and repository from the `origin` remote (a local `git` call, no request);
  * authenticates with GITHUB_TOKEN, else the `gh` command-line tool's login;
  * pages pull requests and issues through GitHub's GraphQL API, newest update first, 100 at a time;
  * keeps every normalised record in `<devkb dir>/github/`, keyed by the item's `updated_at`, so a rebuild stops at
    the first page in which nothing changed;
  * never asks for, and never stores, a description, a review or a comment. The author's login is requested only
    when `"github": {"authors": true}`. Responses are reduced to a fixed list of fields before anything is cached,
    so a field a server sends that was not asked for is dropped too.

When the API cannot be reached or refuses (no credentials, rate limit, network error) the fetch stops, keeps what it
already has, and reports what is missing in its `Fetch` result; the build carries on with the offline layer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from devkb.project_context import load_config

CACHE_FORMAT = 1
PAGE = 100
MAX_PAGES = 400            # 40,000 items per kind: a bound, not an expectation
TIMEOUT_S = 30

Transport = Callable[[str, dict], dict]


class GitHubError(Exception):
    """The API could not be used. The message is shown to the user and recorded in the manifest."""


@dataclass(frozen=True)
class Remote:
    host: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def web(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}"


_REMOTE = re.compile(
    r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?(?P<h1>[^/:]+)(?::\d+)?/|(?:[^@/]+@)?(?P<h2>[^/:]+):)"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")


def parse_remote(url: str) -> Remote | None:
    """`https://host/o/r(.git)`, `git@host:o/r(.git)`, `ssh://git@host/o/r`; credentials in the URL are discarded."""
    m = _REMOTE.match((url or "").strip())
    if not m:
        return None
    return Remote((m.group("h1") or m.group("h2")).lower(), m.group("owner"), m.group("repo"))


def origin_remote(repo_root: Path) -> Remote | None:
    """The `origin` remote, read from the local git configuration. No request is made."""
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_root, capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(out)


def settings(repo_root: Path, flag: bool = False) -> dict:
    """The `github` block of devkb.json with its defaults: online layer off, authors off."""
    block = load_config(repo_root).get("github")
    block = block if isinstance(block, dict) else {}
    return {"enabled": bool(flag or block.get("enabled")), "authors": bool(block.get("authors"))}


def find_token(host: str) -> str | None:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    try:
        out = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def make_transport(remote: Remote, token: str) -> Transport:
    """The real transport: one GraphQL POST. Tests replace this function; nothing else opens a connection."""
    url = "https://api.github.com/graphql" if remote.host == "github.com" else f"https://{remote.host}/api/graphql"

    def send(query: str, variables: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps({"query": query, "variables": variables}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "User-Agent": "devkb", "GraphQL-Features": "sub_issues"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - https URL built above
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            limited = exc.code == 429 or (exc.code == 403 and exc.headers.get("x-ratelimit-remaining") == "0")
            raise GitHubError(("rate limited" if limited else f"HTTP {exc.code}") + f" from {remote.host}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GitHubError(f"{remote.host} unreachable: {getattr(exc, 'reason', exc)}") from exc
        if body.get("errors") and not body.get("data"):
            kinds = ",".join(str(e.get("type") or e.get("message")) for e in body["errors"][:2])
            raise GitHubError(f"GraphQL error from {remote.host}: {kinds}"[:200])
        return body

    return send


# ── queries: only the fields devkb keeps; no body, comments or reviews, author only on request ──────────────────
_PR_FIELDS = """number title state mergedAt updatedAt baseRefName headRefName url
  labels(first: 30) { nodes { name } }
  mergeCommit { oid }
  closingIssuesReferences(first: 50) { nodes { number } }
  commits(first: 100) { totalCount pageInfo { hasNextPage endCursor } nodes { commit { oid } } }"""
_ISSUE_FIELDS = """number title state stateReason url createdAt closedAt updatedAt
  milestone { title }
  labels(first: 30) { nodes { name } }
  issueType { name }
  parent { number repository { nameWithOwner } }
  subIssues(first: 1) { totalCount }"""


def _query(kind: str, authors: bool) -> str:
    fields = _PR_FIELDS if kind == "pullRequests" else _ISSUE_FIELDS
    if authors:
        fields += "\n  author { login }"
    return ("query($owner: String!, $name: String!, $after: String) { repository(owner: $owner, name: $name) { "
            f"{kind}(first: {PAGE}, after: $after, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{ "
            f"totalCount pageInfo {{ hasNextPage endCursor }} nodes {{ {fields} }} }} }} }}")


_MORE_COMMITS = ("query($owner: String!, $name: String!, $number: Int!, $after: String) { repository(owner: $owner, "
                 "name: $name) { pullRequest(number: $number) { commits(first: 100, after: $after) { "
                 "pageInfo { hasNextPage endCursor } nodes { commit { oid } } } } } }")


def _names(conn: Any) -> list[str]:
    return [n["name"] for n in ((conn or {}).get("nodes") or []) if isinstance(n, dict) and n.get("name")]


def normalize_pr(node: dict, authors: bool) -> dict:
    """The record devkb keeps for one pull request. Everything not listed here is dropped."""
    state = {"MERGED": "merged", "CLOSED": "closed"}.get(str(node.get("state")).upper(), "open")
    commits = node.get("commits") or {}
    rec = {
        "number": int(node["number"]), "title": node.get("title") or "", "state": state,
        "merged_at": node.get("mergedAt"), "base": node.get("baseRefName"), "head": node.get("headRefName"),
        "labels": _names(node.get("labels")), "url": node.get("url"), "updated_at": node.get("updatedAt") or "",
        "merge_commit": (node.get("mergeCommit") or {}).get("oid"),
        "commits": [n["commit"]["oid"] for n in (commits.get("nodes") or []) if n and n.get("commit")],
        "commits_total": commits.get("totalCount"),
        "closes": sorted({int(n["number"]) for n in ((node.get("closingIssuesReferences") or {}).get("nodes") or [])
                          if n and n.get("number")}),
    }
    if (commits.get("pageInfo") or {}).get("hasNextPage"):
        rec["_next"] = commits["pageInfo"].get("endCursor")
    if authors and (node.get("author") or {}).get("login"):
        rec["author"] = node["author"]["login"]
    return rec


_LABEL_TYPES = {"bug": "BUG", "epic": "EPIC", "enhancement": "FEATURE", "feature": "FEATURE"}


def ticket_type(issue_type: str | None, labels: list[str]) -> str:
    """ADR-DEVKB-007 §2: the issue's type where the repository uses them, else a label, else ISSUE."""
    if issue_type:
        t = re.sub(r"[^A-Z0-9]+", "_", issue_type.upper()).strip("_")
        return {"ENHANCEMENT": "FEATURE"}.get(t, t) or "ISSUE"
    for label in labels:
        if label.lower() in _LABEL_TYPES:
            return _LABEL_TYPES[label.lower()]
    return "ISSUE"


def normalize_issue(node: dict, authors: bool) -> dict:
    labels = _names(node.get("labels"))
    rec = {
        "number": int(node["number"]), "title": node.get("title") or "",
        "state": "closed" if str(node.get("state")).upper() == "CLOSED" else "open",
        "state_reason": (str(node["stateReason"]).lower() if node.get("stateReason") else None),
        "labels": labels, "milestone": (node.get("milestone") or {}).get("title"), "url": node.get("url"),
        "created_at": node.get("createdAt"), "closed_at": node.get("closedAt"), "updated_at": node.get("updatedAt") or "",
        "ticket_type": ticket_type((node.get("issueType") or {}).get("name"), labels),
        "parent": (node.get("parent") or {}).get("number"),
        "parent_repo": ((node.get("parent") or {}).get("repository") or {}).get("nameWithOwner"),
        "sub_issues": int((node.get("subIssues") or {}).get("totalCount") or 0),
    }
    if authors and (node.get("author") or {}).get("login"):
        rec["author"] = node["author"]["login"]
    return rec


@dataclass
class Fetch:
    """What the online layer produced, and what it could not."""
    requested: bool = False
    remote: Remote | None = None
    prs: dict[int, dict] = field(default_factory=dict)
    issues: dict[int, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    prs_failed: bool = False       # the pull-request listing stopped early (or never started)
    issues_failed: bool = False
    prs_total: int | None = None
    issues_total: int | None = None
    fetched_prs: int = 0       # requests that changed something this build, for reporting
    fetched_issues: int = 0
    fetched_at: str = ""

    @property
    def status(self) -> str:
        if not self.requested:
            return "off"
        if not self.errors:
            return "ok"
        return "partial" if (self.prs or self.issues) else "unreachable"

    @property
    def prs_complete(self) -> bool:
        return self.requested and not self.prs_failed

    @property
    def issues_complete(self) -> bool:
        return self.requested and not self.issues_failed

    def manifest(self) -> dict:
        out: dict[str, Any] = {"status": self.status, "requested": self.requested}
        if self.remote:
            out["repo"] = f"{self.remote.host}/{self.remote.slug}"
        if self.requested:
            out.update(pull_requests=len(self.prs), issues=len(self.issues), pull_requests_total=self.prs_total,
                       issues_total=self.issues_total, fetched_at=self.fetched_at)
        if self.errors:
            out["errors"] = self.errors
        return out


def _load_cache(path: Path, authors: bool) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("format") != CACHE_FORMAT or bool(data.get("authors")) != authors:
        return {}      # another layout, or stored with a different privacy setting: never reused
    items = data.get("items")
    return items if isinstance(items, dict) else {}


def _save_cache(path: Path, items: dict[str, dict], authors: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / ".gitignore").write_text("*\n")
    path.write_text(json.dumps({"format": CACHE_FORMAT, "authors": authors, "items": items}, sort_keys=True))


def _page_all(remote: Remote, transport: Transport, kind: str, cache: dict[str, dict], normalize, authors: bool,
              save: Callable[[], None]) -> tuple[int | None, int, str | None]:
    """Fetch `kind` newest-update first into `cache`. Stops at the first page that held nothing new.
    Returns (total reported by GitHub, items changed, error or None)."""
    cursor, total, changed = None, None, 0
    for _ in range(MAX_PAGES):
        try:
            body = transport(_query(kind, authors), {"owner": remote.owner, "name": remote.repo, "after": cursor})
            conn = body["data"]["repository"][kind]
            nodes = conn["nodes"]
        except GitHubError as exc:
            return total, changed, str(exc)
        except (KeyError, TypeError) as exc:
            return total, changed, f"unexpected response shape ({type(exc).__name__})"
        total = conn.get("totalCount", total)
        page_changed = 0
        for node in nodes:
            if not isinstance(node, dict) or "number" not in node:
                continue
            rec = normalize(node, authors)
            old = cache.get(str(rec["number"]))
            if old is not None and old.get("updated_at") == rec["updated_at"] and "_next" not in old:
                continue
            while "_next" in rec:      # a pull request with more than 100 commits
                try:
                    more = transport(_MORE_COMMITS, {"owner": remote.owner, "name": remote.repo,
                                                     "number": rec["number"], "after": rec.pop("_next")})
                    cm = more["data"]["repository"]["pullRequest"]["commits"]
                except (GitHubError, KeyError, TypeError) as exc:
                    rec["_next"] = "incomplete"
                    save()
                    return total, changed, f"commits of #{rec['number']}: {exc}"
                rec["commits"] += [n["commit"]["oid"] for n in cm["nodes"] if n and n.get("commit")]
                if (cm.get("pageInfo") or {}).get("hasNextPage"):
                    rec["_next"] = cm["pageInfo"]["endCursor"]
            cache[str(rec["number"])] = rec
            page_changed += 1
        changed += page_changed
        save()
        pi = conn.get("pageInfo") or {}
        if page_changed == 0 or not pi.get("hasNextPage"):
            return total, changed, None
        cursor = pi.get("endCursor")
    return total, changed, None


def fetch(repo_root: Path, cache_dir: Path, authors: bool = False, transport: Transport | None = None) -> Fetch:
    """Run the online layer. Never raises for a network or credential problem: it reports it in `Fetch.errors`."""
    result = Fetch(requested=True, fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    remote = origin_remote(repo_root)
    result.remote = remote
    pr_path, issue_path = cache_dir / "pull_requests.json", cache_dir / "issues.json"
    prs, issues = _load_cache(pr_path, authors), _load_cache(issue_path, authors)
    try:
        if remote is None:
            raise GitHubError("no parseable `origin` remote")
        if transport is None:
            token = find_token(remote.host)
            if not token:
                raise GitHubError(f"no credentials for {remote.host} (set GITHUB_TOKEN or run `gh auth login`)")
            transport = make_transport(remote, token)
        result.prs_total, result.fetched_prs, err = _page_all(
            remote, transport, "pullRequests", prs, normalize_pr, authors, lambda: _save_cache(pr_path, prs, authors))
        if err:
            result.errors.append(f"pull requests: {err}")
            result.prs_failed = True
        result.issues_total, result.fetched_issues, err = _page_all(
            remote, transport, "issues", issues, normalize_issue, authors, lambda: _save_cache(issue_path, issues, authors))
        if err:
            result.errors.append(f"issues: {err}")
            result.issues_failed = True
    except GitHubError as exc:
        result.errors.append(str(exc))
        result.prs_failed = result.issues_failed = True
    result.prs = {int(k): v for k, v in prs.items()}
    result.issues = {int(k): v for k, v in issues.items()}
    return result
