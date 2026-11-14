"""The opt-in online layer of ADR-DEVKB-007: read a repository's issues and pull requests from GitHub into a local cache.

Nothing here runs unless the build asks for it (`devkb build --github`, or `{"github": {"enabled": true}}` in
devkb.json). Everything it writes stays in `<devkb dir>/github/cache.json`.

What is kept, and what is not:
  kept      numbers, titles, states, labels, milestone, branch names, urls, timestamps, commit shas, the numbers of
            the issues a pull request closes, a sub-issue's parent
  never     descriptions, comments, review text, emails. Responses are reduced before they reach the cache, so a
            raw body never touches the disk.
  opt-in    the author's login, only with `"github": {"authors": true}`

The cache is keyed by each item's `updated_at`: a rebuild lists only what changed since the last complete listing and
fetches a pull request's commit list only when the pull request itself changed. If the API cannot be reached or the
rate limit is hit, what was fetched is kept, the rest is reported, and the caller builds with the offline layer.
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
from typing import Any, Callable, Iterator

CACHE_VERSION = 1
PER_PAGE = 100
USER_AGENT = "devkb"


class GitHubError(Exception):
    """The API answered, but not usefully (bad credentials, unknown repository, a malformed reply)."""


class Unreachable(GitHubError):
    """No answer at all: no network, DNS failure, timeout."""


class RateLimited(GitHubError):
    """The API refused because the rate limit is used up."""


# ── transport: the only code that touches the network ───────────────────────────────────────────────────────────
def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (https URL built from the origin remote)
            raw, status, hdrs = resp.read(), resp.status, resp.headers
    except urllib.error.HTTPError as exc:
        raw, status, hdrs = exc.read(), exc.code, exc.headers
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise Unreachable(f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    return status, {k.lower(): v for k, v in dict(hdrs).items()}, data


#: Replaced by tests: `(method, url, headers, body) -> (status, lower-case headers, parsed json)`.
transport: Callable[..., tuple[int, dict[str, str], Any]] = _urllib_transport


# ── the remote ──────────────────────────────────────────────────────────────────────────────────────────────────
_REMOTE = re.compile(r"""^(?:(?:https?|ssh|git)://(?:[^@/]+@)?(?P<h1>[^/:]+)(?::\d+)?/|(?:[^@/\s]+@)?(?P<h2>[^/:\s]+):)
                         (?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$""", re.VERBOSE)


def parse_remote(url: str) -> tuple[str, str, str] | None:
    """(host, owner, repo) from an https, ssh or scp-style remote URL, else None."""
    m = _REMOTE.match((url or "").strip())
    if not m:
        return None
    return (m.group("h1") or m.group("h2")).lower(), m.group("owner"), m.group("repo")


def origin_remote(repo_root: Path) -> tuple[str, str, str] | None:
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(repo_root), capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(out)


def api_base(host: str) -> str:
    return "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"


def graphql_url(host: str) -> str:
    return "https://api.github.com/graphql" if host == "github.com" else f"https://{host}/api/graphql"


def find_token(host: str) -> str | None:
    """GITHUB_TOKEN (for github.com only: it is never sent to another host), else the `gh` login for that host."""
    if host == "github.com" and os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    try:
        out = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


# ── client ──────────────────────────────────────────────────────────────────────────────────────────────────────
class Client:
    def __init__(self, host: str, token: str | None) -> None:
        self.host, self.token, self.requests = host, token, 0

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _check(self, status: int, headers: dict[str, str], data: Any, what: str) -> None:
        text = str((data or {}).get("message", "")) if isinstance(data, dict) else ""
        if status in (403, 429) and (headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
                                     or "rate limit" in text.lower()):
            raise RateLimited(f"rate limit reached at {what}")
        if status == 401:
            raise GitHubError(f"authentication failed at {what}")
        if status >= 400:
            raise GitHubError(f"HTTP {status} at {what}")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
        url = f"{api_base(self.host)}{path}{query}"
        self.requests += 1
        status, headers, data = transport("GET", url, self._headers(), None)
        self._check(status, headers, data, path)
        return data

    def pages(self, path: str, params: dict[str, Any]) -> Iterator[list[dict]]:
        page = 1
        while True:
            data = self.get(path, {**params, "per_page": PER_PAGE, "page": page})
            if not isinstance(data, list):
                raise GitHubError(f"unexpected reply at {path}")
            yield data
            if len(data) < PER_PAGE:
                return
            page += 1

    def graphql(self, query: str, variables: dict[str, Any]) -> dict:
        self.requests += 1
        body = json.dumps({"query": query, "variables": variables}).encode()
        status, headers, data = transport("POST", graphql_url(self.host), {**self._headers(), "Content-Type": "application/json"}, body)
        self._check(status, headers, data, "graphql")
        if not isinstance(data, dict) or not data.get("data"):
            errors = (data or {}).get("errors") if isinstance(data, dict) else None
            if errors and any(e.get("type") == "RATE_LIMITED" for e in errors if isinstance(e, dict)):
                raise RateLimited("rate limit reached at graphql")
            raise GitHubError("graphql reply carried no data")
        return data["data"]


# ── reduction: what may be written down ─────────────────────────────────────────────────────────────────────────
def _labels(item: dict) -> list[str]:
    return sorted(str(l.get("name")) for l in item.get("labels") or [] if isinstance(l, dict) and l.get("name"))


def _author(item: dict, authors: bool) -> dict:
    login = (item.get("user") or {}).get("login") if authors else None
    return {"author": login} if login else {}


def reduce_issue(item: dict, authors: bool) -> dict:
    parent = item.get("parent_issue_url") or ""
    pm = re.search(r"/issues/(\d+)$", parent)
    return {"number": item["number"], "title": item.get("title") or "", "state": item.get("state"),
            "state_reason": item.get("state_reason"), "labels": _labels(item),
            "milestone": (item.get("milestone") or {}).get("title"), "url": item.get("html_url"),
            "created_at": item.get("created_at"), "closed_at": item.get("closed_at"), "updated_at": item.get("updated_at"),
            "type": (item.get("type") or {}).get("name") if isinstance(item.get("type"), dict) else None,
            "parent": int(pm.group(1)) if pm else None,
            "sub_issues": int((item.get("sub_issues_summary") or {}).get("total") or 0),
            **_author(item, authors)}


def reduce_pr(item: dict, authors: bool) -> dict:
    return {"number": item["number"], "title": item.get("title") or "", "state": item.get("state"),
            "merged_at": item.get("merged_at"), "base": (item.get("base") or {}).get("ref"),
            "head": (item.get("head") or {}).get("ref"), "labels": _labels(item), "url": item.get("html_url"),
            "updated_at": item.get("updated_at"), "merge_commit_sha": item.get("merge_commit_sha"),
            **_author(item, authors)}


# ── cache ───────────────────────────────────────────────────────────────────────────────────────────────────────
def empty_cache(slug: str, authors: bool = False) -> dict:
    return {"version": CACHE_VERSION, "repo": slug, "authors": authors, "issues_since": None, "prs_since": None, "closes_since": None,
            "issues": {}, "prs": {}, "commits": {}, "closes": {}}


def load_cache(cache_dir: Path, slug: str, authors: bool) -> dict:
    try:
        cache = json.loads((cache_dir / "cache.json").read_text())
    except (OSError, ValueError):
        return empty_cache(slug, authors)
    if not isinstance(cache, dict) or cache.get("version") != CACHE_VERSION or cache.get("repo") != slug:
        return empty_cache(slug, authors)
    if authors and not cache.get("authors"):  # logins were never fetched for what is cached: fetch it all again
        return empty_cache(slug, authors)
    cache["authors"] = authors
    if not authors:  # an earlier build with authors on must not leak into this one
        for kind in ("issues", "prs"):
            for rec in cache.get(kind, {}).values():
                rec.pop("author", None)
    return cache


def save_cache(cache_dir: Path, cache: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / "cache.json.tmp"
    tmp.write_text(json.dumps(cache, sort_keys=True))
    tmp.replace(cache_dir / "cache.json")


# ── sync ────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Report:
    """What the online layer did, written to the manifest and shown in answers' coverage."""
    status: str = "ok"                     # ok | partial | unreachable
    repo: str = ""
    requests: int = 0
    issues: int = 0
    pull_requests: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"enabled": True, "status": self.status, "repo": self.repo, "requests": self.requests,
                "issues": self.issues, "pull_requests": self.pull_requests, "errors": self.errors}


_CLOSING_QUERY = """query($owner:String!,$repo:String!,$after:String){repository(owner:$owner,name:$repo){
pullRequests(first:100,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){pageInfo{hasNextPage endCursor}
nodes{number updatedAt closingIssuesReferences(first:50){nodes{number repository{nameWithOwner}}}}}}}"""


def _sync_issues(c: Client, owner: str, repo: str, cache: dict, authors: bool) -> None:
    params: dict[str, Any] = {"state": "all", "sort": "updated", "direction": "desc"}
    if cache["issues_since"]:
        params["since"] = cache["issues_since"]
    newest = cache["issues_since"] or ""
    for page in c.pages(f"/repos/{owner}/{repo}/issues", params):
        for item in page:
            newest = max(newest, item.get("updated_at") or "")
            if "pull_request" not in item:
                cache["issues"][str(item["number"])] = reduce_issue(item, authors)
    cache["issues_since"] = newest or cache["issues_since"]


def _sync_prs(c: Client, owner: str, repo: str, cache: dict, authors: bool) -> None:
    boundary = cache["prs_since"] or ""
    newest = boundary
    for page in c.pages(f"/repos/{owner}/{repo}/pulls", {"state": "all", "sort": "updated", "direction": "desc"}):
        for item in page:
            upd = item.get("updated_at") or ""
            if boundary and upd < boundary:
                cache["prs_since"] = newest
                return
            newest = max(newest, upd)
            cache["prs"][str(item["number"])] = reduce_pr(item, authors)
    cache["prs_since"] = newest or cache["prs_since"]


def _sync_commits(c: Client, owner: str, repo: str, cache: dict) -> None:
    """The commit list of each merged pull request whose list is missing or older than the pull request."""
    for key in sorted(cache["prs"], key=int, reverse=True):
        pr = cache["prs"][key]
        have = cache["commits"].get(key)
        if not pr.get("merged_at") or (have and have["for"] == pr["updated_at"]):
            continue
        shas: list[str] = []
        for page in c.pages(f"/repos/{owner}/{repo}/pulls/{key}/commits", {}):
            shas += [x["sha"] for x in page if isinstance(x, dict) and x.get("sha")]
        cache["commits"][key] = {"for": pr["updated_at"], "shas": shas}


def _sync_closing(c: Client, owner: str, repo: str, cache: dict) -> None:
    boundary = cache["closes_since"] or ""
    newest, after = boundary, None
    slug = f"{owner}/{repo}".lower()
    while True:
        data = c.graphql(_CLOSING_QUERY, {"owner": owner, "repo": repo, "after": after})
        prs = ((data.get("repository") or {}).get("pullRequests")) or {}
        for node in prs.get("nodes") or []:
            upd = node.get("updatedAt") or ""
            if boundary and upd < boundary:
                cache["closes_since"] = newest
                return
            newest = max(newest, upd)
            refs = (node.get("closingIssuesReferences") or {}).get("nodes") or []
            cache["closes"][str(node["number"])] = sorted(
                r["number"] for r in refs if str((r.get("repository") or {}).get("nameWithOwner", slug)).lower() == slug)
        page = prs.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    cache["closes_since"] = newest or cache["closes_since"]


def sync(repo_root: Path, cache_dir: Path, authors: bool) -> tuple[dict | None, Report]:
    """Bring the cache up to date. Returns (cache, report); the cache is None when nothing can be said about this
    repository at all (no GitHub-style origin remote)."""
    remote = origin_remote(repo_root)
    if remote is None:
        rep = Report(status="unreachable", errors=["no parseable origin remote: the repository's host is unknown"])
        return None, rep
    host, owner, repo = remote
    slug = f"{host}/{owner}/{repo}"
    rep = Report(repo=slug)
    cache = load_cache(cache_dir, slug, authors)
    token = find_token(host)
    client = Client(host, token)
    phases: list[tuple[str, Callable[[], None]]] = [
        ("issues", lambda: _sync_issues(client, owner, repo, cache, authors)),
        ("pull requests", lambda: _sync_prs(client, owner, repo, cache, authors)),
        ("pull request commits", lambda: _sync_commits(client, owner, repo, cache)),
    ]
    if token:
        phases.append(("closing links", lambda: _sync_closing(client, owner, repo, cache)))
    else:
        rep.errors.append("closing links not fetched: GraphQL needs a token (set GITHUB_TOKEN or run `gh auth login`)")
    first = True
    for name, run in phases:
        try:
            run()
        except Unreachable as exc:
            rep.errors.append(f"{name}: GitHub unreachable ({exc})")
            rep.status = "unreachable" if first and not cache["issues"] and not cache["prs"] else "partial"
            break
        except RateLimited as exc:
            rep.errors.append(f"{name}: {exc}; kept what was fetched, the rest waits for the next build")
            rep.status = "partial"
            break
        except GitHubError as exc:
            rep.errors.append(f"{name}: {exc}")
            rep.status = "partial"
        first = False
    if rep.errors and rep.status == "ok":
        rep.status = "partial"
    rep.requests, rep.issues, rep.pull_requests = client.requests, len(cache["issues"]), len(cache["prs"])
    try:
        save_cache(cache_dir, cache)
    except OSError as exc:
        rep.errors.append(f"cache not written: {exc}")
    return cache, rep


@dataclass(frozen=True)
class Options:
    enabled: bool = False
    authors: bool = False


def options(cfg: dict, flag: bool = False) -> Options:
    """`devkb build --github` or `{"github": {"enabled": true, "authors": true}}` in devkb.json."""
    gh = cfg.get("github") if isinstance(cfg, dict) and isinstance(cfg.get("github"), dict) else {}
    return Options(enabled=bool(flag or gh.get("enabled")), authors=bool(gh.get("authors")))
