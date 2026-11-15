"""The online GitHub layer's client and local cache (ADR-DEVKB-007 item 6).

Opt-in only: nothing here runs unless `devkb build --github` or `{"github": {"enabled": true}}` asked for it. Everything
the build learns is projected onto an allow-list of fields BEFORE it is cached or returned, so descriptions, review
text, emails and author logins never reach `.devkb/` (the login only when `"github": {"authors": true}`).

  host and repository   from the `origin` remote
  authentication        GITHUB_TOKEN, else the `gh` command-line tool's login, else none (public data, low rate limit)
  cache                 `<devkb dir>/github/*.json`, each item keyed by its `updated_at`, so a rebuild fetches only
                        what changed: the lists are read newest-updated first and stop at the first unchanged item
  failure               an unreachable or rate-limited API never fails a build: what was cached is used, what could
                        not be fetched is recorded in `Result.errors`, and the build says so in the manifest
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PAGE = 100
GRAPHQL_PAGE = 50
CACHE_DIR = "github"
TIMEOUT = 30

_REMOTE = re.compile(r"^(?:(?:ssh|https?|git)://(?:[^@/]+@)?|[^@/\s]+@)(?P<host>[^/:]+)(?::\d+)?[:/](?P<path>[^\s]+?)(?:\.git)?/?$")


class GitHubError(Exception):
    """An API call that did not succeed; `kind` is `unreachable`, `rate-limited`, `unauthorized`, `not-found` or `error`."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def parse_remote(url: str) -> tuple[str, str, str] | None:
    """(host, owner, repo) from a git remote URL, or None when it is not `<host>/<owner>/<repo>` shaped."""
    m = _REMOTE.match(url.strip())
    if not m:
        return None
    parts = m.group("path").strip("/").split("/")
    return (m.group("host").lower(), parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def origin(repo_root: Path) -> tuple[str, str, str] | None:
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_root, capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(out) if out.strip() else None


def api_base(host: str) -> str:
    return "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"


def find_token(host: str) -> str | None:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def http_request(url: str, token: str | None, body: dict | None = None) -> Any:
    """GET (or POST a JSON body) and return the decoded JSON. The one place that touches the network: tests replace it."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "devkb", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (https only, host from origin)
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
        if exc.code == 429 or (exc.code == 403 and (remaining == "0" or "rate limit" in (exc.reason or "").lower())):
            raise GitHubError("rate-limited", f"HTTP {exc.code}: rate limit reached") from exc
        kind = {401: "unauthorized", 404: "not-found"}.get(exc.code, "error")
        raise GitHubError(kind, f"HTTP {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise GitHubError("unreachable", f"{type(exc).__name__}: {exc}") from exc


# ── projections: the allow-list that keeps descriptions and people out ─────────────────────────────────────────
def _labels(item: dict) -> list[str]:
    return sorted(str(lb.get("name") if isinstance(lb, dict) else lb) for lb in item.get("labels") or [])


def project_issue(item: dict, authors: bool) -> dict:
    out = {"number": item["number"], "title": item.get("title") or "", "state": item.get("state") or "open",
           "state_reason": item.get("state_reason"), "labels": _labels(item),
           "milestone": (item.get("milestone") or {}).get("title") if isinstance(item.get("milestone"), dict) else None,
           "url": item.get("html_url"), "created_at": item.get("created_at"), "closed_at": item.get("closed_at"),
           "updated_at": item.get("updated_at"),
           "issue_type": (item.get("type") or {}).get("name") if isinstance(item.get("type"), dict) else None,
           "sub_issues": int((item.get("sub_issues_summary") or {}).get("total") or 0),
           "parent": _number_at_end(item.get("parent_issue_url"))}
    if authors:
        out["author"] = (item.get("user") or {}).get("login")
    return out


def project_pull(item: dict, authors: bool) -> dict:
    merged_at = item.get("merged_at")
    out = {"number": item["number"], "title": item.get("title") or "",
           "state": "merged" if merged_at else ("open" if item.get("state") == "open" else "closed"),
           "merged_at": merged_at, "base": (item.get("base") or {}).get("ref"), "head": (item.get("head") or {}).get("ref"),
           "labels": _labels(item), "url": item.get("html_url"), "updated_at": item.get("updated_at"),
           "merge_commit": item.get("merge_commit_sha")}
    if authors:
        out["author"] = (item.get("user") or {}).get("login")
    return out


def _number_at_end(url: Any) -> int | None:
    m = re.search(r"/(\d+)$", url or "")
    return int(m.group(1)) if m else None


_GQL = """query($owner:String!,$name:String!,$after:String){repository(owner:$owner,name:$name){
pullRequests(first:%d,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){pageInfo{hasNextPage endCursor}
nodes{number updatedAt mergeCommit{oid} commits(first:100){totalCount nodes{commit{oid}}}
closingIssuesReferences(first:50){nodes{number repository{nameWithOwner}}}}}}}""" % GRAPHQL_PAGE


# ── the cache ──────────────────────────────────────────────────────────────────────────────────────────────────
class Cache:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def load(self, name: str) -> dict[str, dict]:
        try:
            data = json.loads((self.dir / f"{name}.json").read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, name: str, data: dict[str, dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.json").write_text(json.dumps(data, sort_keys=True))


@dataclass
class Result:
    """What the online layer knew when the build ended. `errors` is empty only when every endpoint was read to the end."""
    issues: dict[int, dict] = field(default_factory=dict)
    pulls: dict[int, dict] = field(default_factory=dict)
    links: dict[int, dict] = field(default_factory=dict)   # PR number -> {commits, commits_total, merge_commit, closes}
    errors: list[str] = field(default_factory=list)
    requests: int = 0
    authenticated: bool = False
    repo: str = ""
    skipped: str = ""                                       # why nothing was attempted, if so

    def summary(self) -> dict:
        return {"enabled": True, "repo": self.repo, "authenticated": self.authenticated, "requests": self.requests,
                "issues": len(self.issues), "pull_requests": len(self.pulls), "pull_requests_linked": len(self.links),
                "errors": self.errors, "complete": not self.errors and not self.skipped,
                **({"skipped": self.skipped} if self.skipped else {})}


def _paged(cache: dict[str, dict], fetch_page, project, key: str, res: Result, what: str) -> None:
    """Read a list newest-updated first, stopping at the first item the cache already holds unchanged."""
    page = 1
    while True:
        try:
            items = fetch_page(page)
        except GitHubError as exc:
            res.errors.append(f"{what}: {exc.kind} ({exc})")
            return
        res.requests += 1
        for item in items:
            row = project(item)
            if (cache.get(str(row[key])) or {}).get("updated_at") == row.get("updated_at"):
                return
            cache[str(row[key])] = row
        if len(items) < PAGE:
            return
        page += 1


def fetch(repo_root: Path, cache_dir: Path, authors: bool, request=None) -> Result:
    """Refresh the cache from GitHub and return everything it holds. Never raises for a network or API failure."""
    request = request or http_request
    res = Result()
    where = origin(repo_root)
    if where is None:
        res.skipped = "no `origin` remote of the form <host>/<owner>/<repo>"
        return res
    host, owner, repo = where
    res.repo = f"{host}/{owner}/{repo}"
    token = find_token(host)
    res.authenticated = token is not None
    base = f"{api_base(host)}/repos/{owner}/{repo}"
    cache = Cache(cache_dir)
    issues, pulls, links = cache.load("issues"), cache.load("pulls"), cache.load("links")
    if not authors:  # a cache written while logins were allowed must not carry them into this build
        for table in (issues, pulls):
            for row in table.values():
                row.pop("author", None)
    if not token:
        res.errors.append("no GITHUB_TOKEN or `gh` login: commit lists and closing links need one (GraphQL), "
                          "so only issues and pull request records were fetched")

    def get(url: str) -> Any:
        return request(url, token)

    # Issues (type, labels, milestone, sub-issue links). The endpoint also lists pull requests; those come from /pulls.
    def issue_page(page: int) -> list[dict]:
        return get(f"{base}/issues?state=all&sort=updated&direction=desc&per_page={PAGE}&page={page}")

    _paged_issues(issues, issue_page, authors, res)
    _paged(pulls, lambda p: get(f"{base}/pulls?state=all&sort=updated&direction=desc&per_page={PAGE}&page={p}"),
           lambda it: project_pull(it, authors), "number", res, "pull requests")

    if token:
        cursor = None
        while True:
            try:
                data = request(f"{api_base(host)}/graphql" if host == "github.com" else f"https://{host}/api/graphql", token,
                               {"query": _GQL, "variables": {"owner": owner, "name": repo, "after": cursor}})
            except GitHubError as exc:
                res.errors.append(f"commit lists and closing links: {exc.kind} ({exc})")
                break
            res.requests += 1
            conn = (((data or {}).get("data") or {}).get("repository") or {}).get("pullRequests")
            if not conn:
                res.errors.append("commit lists and closing links: unexpected GraphQL reply "
                                  + json.dumps((data or {}).get("errors") or "")[:200])
                break
            unchanged = False
            for node in conn.get("nodes") or []:
                if (links.get(str(node["number"])) or {}).get("updated_at") == node.get("updatedAt"):
                    unchanged = True
                    break
                commits = node.get("commits") or {}
                links[str(node["number"])] = {
                    "updated_at": node.get("updatedAt"), "merge_commit": (node.get("mergeCommit") or {}).get("oid"),
                    "commits": [c["commit"]["oid"] for c in commits.get("nodes") or []],
                    "commits_total": commits.get("totalCount"),
                    "closes": sorted({r["number"] for r in (node.get("closingIssuesReferences") or {}).get("nodes") or []
                                      if (r.get("repository") or {}).get("nameWithOwner", "").lower() == f"{owner}/{repo}".lower()})}
            info = conn.get("pageInfo") or {}
            if unchanged or not info.get("hasNextPage"):
                break
            cursor = info.get("endCursor")

    for name, data in (("issues", issues), ("pulls", pulls), ("links", links)):
        try:
            cache.save(name, data)
        except OSError as exc:
            res.errors.append(f"cache {name}: {exc}")
    res.issues = {int(k): v for k, v in issues.items()}
    res.pulls = {int(k): v for k, v in pulls.items()}
    res.links = {int(k): v for k, v in links.items()}
    return res


def _paged_issues(cache: dict[str, dict], fetch_page, authors: bool, res: Result) -> None:
    """Like `_paged`, but the issues endpoint mixes in pull requests, which are dropped after the page-size check."""
    page = 1
    while True:
        try:
            items = fetch_page(page)
        except GitHubError as exc:
            res.errors.append(f"issues: {exc.kind} ({exc})")
            return
        res.requests += 1
        for item in items:
            if "pull_request" in item:
                continue
            row = project_issue(item, authors)
            if (cache.get(str(row["number"])) or {}).get("updated_at") == row["updated_at"]:
                return
            cache[str(row["number"])] = row
        if len(items) < PAGE:
            return
        page += 1
