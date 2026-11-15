"""The opt-in online layer for pull requests and hosted issues (ADR-DEVKB-007 item 6).

Nothing here runs unless a build asks for it (`devkb build --github`, or `{"github": {"enabled": true}}` in
devkb.json). It reads one repository's pull requests, issues, each pull request's commit list and the issues each
pull request closes, keeps a trimmed copy in `.devkb/github/`, and says what it could not fetch.

Privacy: the records kept here hold titles, states, labels, branch names, dates and numbers. They never hold a
description, a review or a comment, and hold an author login only when `"github": {"authors": true}`.

Tests replace `TRANSPORT` with a fake; the default one is the only code in devkb that opens a network connection.
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
from typing import Any, Callable

#: transport(method, url, headers, body) -> (status, response headers with lower-case names, decoded JSON)
Transport = Callable[[str, str, dict, "bytes | None"], "tuple[int, dict, Any]"]

PAGE = 100
COMMITS_CAP = 250          # the API returns at most this many commits for one pull request
GRAPHQL_BATCH = 40
DEFAULT_MAX_REQUESTS = 5000
CACHE_SCHEMA = 1


class GitHubError(Exception):
    """kind: unreachable | rate_limited | unauthorized | not_found | error"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def default_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (https URL built from the origin remote)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"null")
        except ValueError:
            payload = None
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, payload


#: replaced by tests; None means default_transport
TRANSPORT: Transport | None = None


# ── which repository, which credentials ───────────────────────────────────────
_REMOTE = (re.compile(r"^(?:https?|ssh|git)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"),
           re.compile(r"^(?:[^@/]+@)?(?P<host>[^/:]+):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"))


def parse_remote(url: str) -> tuple[str, str, str] | None:
    for rx in _REMOTE:
        m = rx.match(url.strip())
        if m:
            return m["host"].lower(), m["owner"], m["repo"]
    return None


def origin(repo_root: Path) -> tuple[str, str, str] | None:
    """(host, owner, repo) of the `origin` remote, read from local git config only."""
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_root, capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(out) if out.strip() else None


def is_github_host(host: str) -> bool:
    return host == "github.com" or host.startswith("github.") or ".github." in host


def find_token(host: str) -> str | None:
    """GITHUB_TOKEN, else the `gh` command-line tool's login. None when neither exists."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    try:
        r = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


# ── the client ────────────────────────────────────────────────────────────────
class Client:
    def __init__(self, host: str, owner: str, repo: str, token: str | None, max_requests: int = DEFAULT_MAX_REQUESTS) -> None:
        self.host, self.owner, self.repo, self.token = host, owner, repo, token
        self.max_requests = max_requests
        self.requests = 0
        if host == "github.com":
            self.api, self.graphql_url = "https://api.github.com", "https://api.github.com/graphql"
        else:
            self.api, self.graphql_url = f"https://{host}/api/v3", f"https://{host}/api/graphql"

    def _call(self, method: str, url: str, body: bytes | None = None) -> Any:
        if self.requests >= self.max_requests:
            raise GitHubError("rate_limited", f"request budget of {self.max_requests} reached (github.max_requests)")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "devkb", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        self.requests += 1
        try:
            status, resp_headers, payload = (TRANSPORT or default_transport)(method, url, headers, body)
        except (OSError, ValueError) as exc:  # URLError and timeouts are OSErrors
            raise GitHubError("unreachable", f"{self.host} unreachable: {exc}") from exc
        if status in (403, 429):
            text = json.dumps(payload) if payload else ""
            if resp_headers.get("x-ratelimit-remaining") == "0" or status == 429 or "rate limit" in text.lower():
                raise GitHubError("rate_limited", f"{self.host} rate limit reached")
            raise GitHubError("unauthorized", f"{self.host} refused the request (HTTP {status})")
        if status == 401:
            raise GitHubError("unauthorized", f"{self.host} rejected the credentials (HTTP 401)")
        if status == 404:
            raise GitHubError("not_found", f"{self.owner}/{self.repo} not found or not visible (HTTP 404)")
        if status >= 500:
            raise GitHubError("unreachable", f"{self.host} answered HTTP {status}")
        if status >= 400:
            raise GitHubError("error", f"{self.host} answered HTTP {status}")
        return payload

    def get(self, path: str, **params: Any) -> Any:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self._call("GET", f"{self.api}/repos/{self.owner}/{self.repo}/{path}" + (f"?{query}" if query else ""))

    def pages(self, path: str, max_pages: int = 10**6, **params: Any):
        for page in range(1, max_pages + 1):
            rows = self.get(path, per_page=PAGE, page=page, **params)
            if not isinstance(rows, list):
                raise GitHubError("error", f"unexpected answer for {path}")
            yield rows
            if len(rows) < PAGE:
                return

    def closing_issues(self, numbers: list[int]) -> dict[int, list[dict]]:
        """GitHub's own record of the issues each pull request closes (GraphQL `closingIssuesReferences`)."""
        fields = "closingIssuesReferences(first: 50) { nodes { number title state url repository { nameWithOwner } } }"
        body = "".join(f"p{n}: pullRequest(number: {n}) {{ {fields} }} " for n in numbers)
        query = f'query {{ repository(owner: "{self.owner}", name: "{self.repo}") {{ {body} }} }}'
        data = self._call("POST", self.graphql_url, json.dumps({"query": query}).encode())
        repo = ((data or {}).get("data") or {}).get("repository") or {}
        if not repo:
            raise GitHubError("error", "GraphQL answered without a repository: " + json.dumps((data or {}).get("errors"))[:200])
        out: dict[int, list[dict]] = {}
        same = f"{self.owner}/{self.repo}".lower()
        for n in numbers:
            node = repo.get(f"p{n}")
            if node is None:
                continue
            out[n] = [{"number": i["number"], "title": i.get("title"), "state": (i.get("state") or "").lower(), "url": i.get("url")}
                      for i in node["closingIssuesReferences"]["nodes"]
                      if (i.get("repository") or {}).get("nameWithOwner", "").lower() == same]
        return out


# ── trimmed records: only what the graph stores ──────────────────────────────
def _label_names(labels: Any) -> list[str]:
    return sorted(str(l.get("name") if isinstance(l, dict) else l) for l in labels or [] if l)


def _number_from_url(url: str | None) -> int | None:
    m = re.search(r"/issues/(\d+)$", url or "")
    return int(m.group(1)) if m else None


def trim_pull(raw: dict, authors: bool) -> dict:
    rec = {"number": raw["number"], "title": raw.get("title") or "", "merged_at": raw.get("merged_at"),
           "state": "merged" if raw.get("merged_at") else (raw.get("state") or "open"),
           "base": (raw.get("base") or {}).get("ref"), "head": (raw.get("head") or {}).get("ref"),
           "labels": _label_names(raw.get("labels")), "url": raw.get("html_url"),
           "merge_commit_sha": raw.get("merge_commit_sha"), "updated_at": raw.get("updated_at")}
    if authors and (raw.get("user") or {}).get("login"):
        rec["author"] = raw["user"]["login"]
    return rec


def trim_issue(raw: dict, authors: bool) -> dict:
    summary = raw.get("sub_issues_summary") or {}
    rec = {"number": raw["number"], "title": raw.get("title") or "", "state": raw.get("state") or "open",
           "state_reason": raw.get("state_reason"), "labels": _label_names(raw.get("labels")),
           "milestone": (raw.get("milestone") or {}).get("title"), "url": raw.get("html_url"),
           "created_at": raw.get("created_at"), "closed_at": raw.get("closed_at"), "updated_at": raw.get("updated_at"),
           "type": (raw.get("type") or {}).get("name") if isinstance(raw.get("type"), dict) else None,
           "parent": _number_from_url(raw.get("parent_issue_url")), "sub_issues": int(summary.get("total") or 0)}
    if authors and (raw.get("user") or {}).get("login"):
        rec["author"] = raw["user"]["login"]
    return rec


# ── the local cache ──────────────────────────────────────────────────────────
class Cache:
    """`.devkb/github/{meta,pulls,issues}.json`, keyed by each item's `updated_at`. Discarded when it was written for
    another repository, another schema or another `authors` setting (a cache written without logins must not be read
    as one that has them)."""

    def __init__(self, directory: Path, slug: str, authors: bool) -> None:
        self.dir = directory
        self.meta = {"schema": CACHE_SCHEMA, "repo": slug, "authors": authors, "pulls_complete": False, "issues_complete": False}
        self.pulls: dict[str, dict] = {}
        self.issues: dict[str, dict] = {}
        try:
            meta = json.loads((directory / "meta.json").read_text())
            if all(meta.get(k) == self.meta[k] for k in ("schema", "repo", "authors")):
                self.meta = {**self.meta, **meta}
                self.pulls = json.loads((directory / "pulls.json").read_text())
                self.issues = json.loads((directory / "issues.json").read_text())
        except (OSError, ValueError):
            self.meta["pulls_complete"] = self.meta["issues_complete"] = False
            self.pulls, self.issues = {}, {}

    def save(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            for name, data in (("pulls", self.pulls), ("issues", self.issues), ("meta", self.meta)):
                tmp = self.dir / f"{name}.json.tmp"
                tmp.write_text(json.dumps(data, sort_keys=True))
                tmp.replace(self.dir / f"{name}.json")
        except OSError:
            pass


@dataclass
class Snapshot:
    """What the API (and the cache) said. `pulls[n]` may carry `commits` (a list of shas) and `closes` (issue numbers)
    once those were fetched; a missing key means "not known", never "none"."""
    slug: str
    pulls: dict[int, dict] = field(default_factory=dict)
    issues: dict[int, dict] = field(default_factory=dict)
    issue_titles: dict[int, dict] = field(default_factory=dict)  # closing-record issues the listing did not return
    pulls_complete: bool = False
    issues_complete: bool = False
    problems: list[str] = field(default_factory=list)
    requests: int = 0
    cached: int = 0

    def status(self) -> str:
        if not self.problems:
            return "complete"
        return "unreachable" if not (self.pulls or self.issues) else "partial"

    def report(self, authors: bool) -> dict:
        n = len(self.pulls)
        return {"enabled": True, "repo": self.slug, "status": self.status(), "problems": self.problems,
                "requests": self.requests, "cached_items": self.cached, "pull_requests": n, "issues": len(self.issues),
                "commit_lists": sum(1 for p in self.pulls.values() if "commits" in p),
                "closing_records": sum(1 for p in self.pulls.values() if "closes" in p), "authors": authors}


def fetch(client: Client, cache: Cache, authors: bool) -> Snapshot:
    """Read pull requests, issues, commit lists and closing records, newest-updated first, reusing cached details for
    every item whose `updated_at` has not changed. A failure stops that stage, is recorded, and everything already
    fetched (and the cache) is kept; this function never raises for a network or API problem."""
    snap = Snapshot(slug=f"{client.owner}/{client.repo}")

    def listing(kind: str, path: str, cached: dict[str, dict], trim: Callable[[dict, bool], dict], extra: dict) -> bool:
        """Page newest-updated first; stop early when a whole page is unchanged and the previous listing was complete."""
        was_complete = bool(cache.meta.get(f"{kind}_complete"))
        try:
            for rows in client.pages(path, state="all", sort="updated", direction="desc", **extra):
                unchanged = 0
                for raw in rows:
                    if kind == "issues" and "pull_request" in raw:
                        unchanged += 1
                        continue
                    rec = trim(raw, authors)
                    old = cached.get(str(rec["number"]))
                    if old and old.get("updated_at") == rec["updated_at"]:
                        rec = old
                        unchanged += 1
                        snap.cached += 1
                    cached[str(rec["number"])] = rec
                if was_complete and unchanged == len(rows):
                    return True
            return True
        except GitHubError as exc:
            snap.problems.append(f"{kind}: {exc}")
            return False

    cache.meta["pulls_complete"] = listing("pulls", "pulls", cache.pulls, trim_pull, {})
    cache.meta["issues_complete"] = listing("issues", "issues", cache.issues, trim_issue, {})
    snap.pulls_complete, snap.issues_complete = bool(cache.meta["pulls_complete"]), bool(cache.meta["issues_complete"])

    todo = sorted((p for p in cache.pulls.values() if "commits" not in p), key=lambda p: -p["number"])
    for rec in todo:
        try:
            shas: list[str] = []
            for rows in client.pages(f"pulls/{rec['number']}/commits", max_pages=COMMITS_CAP // PAGE + 1):
                shas += [c["sha"] for c in rows]
            rec["commits"] = shas
        except GitHubError as exc:
            if exc.kind != "not_found":
                snap.problems.append(f"pull request commit lists: {exc}")
                break
    if client.token is None:
        if any("closes" not in p for p in cache.pulls.values()):
            snap.problems.append("closing-issue records: GitHub's GraphQL API needs a token (GITHUB_TOKEN or `gh auth login`); "
                                 "closing links stay at the offline layer's confidence")
    else:
        pending = sorted((p["number"] for p in cache.pulls.values() if "closes" not in p), reverse=True)
        for i in range(0, len(pending), GRAPHQL_BATCH):
            batch = pending[i:i + GRAPHQL_BATCH]
            try:
                got = client.closing_issues(batch)
            except GitHubError as exc:
                snap.problems.append(f"closing-issue records: {exc}")
                break
            for n, issues in got.items():
                cache.pulls[str(n)]["closes"] = [x["number"] for x in issues]
                for x in issues:
                    snap.issue_titles[x["number"]] = x

    cache.save()
    snap.requests = client.requests
    snap.pulls = {int(k): v for k, v in cache.pulls.items()}
    snap.issues = {int(k): v for k, v in cache.issues.items()}
    return snap
