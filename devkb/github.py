"""The opt-in online layer of ADR-DEVKB-007: pull requests and issues from GitHub, cached on this machine.

Nothing here runs unless the caller asked for it (`devkb build --github`, or `{"github": {"enabled": true}}` in
devkb.json). A build without that never imports a client, never reads a token and never opens a socket.

  settings()       what the repository's devkb.json and the command line ask for
  origin_remote()  host, owner and repository from the `origin` remote, credentials dropped
  fetch()          pull requests and issues, as plain dicts holding only the fields devkb stores
  cache            `<devkb dir>/github/{pull_requests,issues}.json`, keyed by each item's `updated_at`

What is requested, and so what can be stored: numbers, titles, states, labels, branch names, merge commit, commit ids,
the issues a pull request closes, issue type, milestone and sub-issue parent. Never a description, a comment, a review
or an email. An author login is requested only when `"github": {"authors": true}`.

Failure is a result, not an exception: an unreachable or rate-limited API leaves the build with the offline layer and
whatever the cache already held, and `fetch()` says which (`report`), so every affected answer can state its coverage.
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
from typing import Callable

from devkb.project_context import load_config

#: transport(query, variables) -> the decoded JSON response `{"data": ..., "errors": ...}`. Raises GitHubError.
Transport = Callable[[str, dict], dict]

PAGE = 100
MAX_COMMIT_PAGES = 5            # the API lists at most 250 commits of a pull request anyway
CACHE_VERSION = 2             # 2: a listing records whether it finished, and where to resume


class GitHubError(Exception):
    """kind: unreachable, rate-limited, unauthorized, not-found, schema or graphql."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind, self.message = kind, message


# ── settings and remote ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    authors: bool = False
    host: str | None = None


def settings(repo_root: Path, flag: bool | None = None) -> Settings:
    """`flag` is the command line: True for --github, False for --no-github, None to follow devkb.json."""
    raw = load_config(repo_root).get("github")
    cfg = raw if isinstance(raw, dict) else {}
    enabled = bool(cfg.get("enabled")) if flag is None else flag
    host = cfg.get("host") if isinstance(cfg.get("host"), str) and cfg.get("host") else None
    return Settings(enabled=enabled, authors=cfg.get("authors") is True, host=host)


_MERGE_FROM = re.compile(r"^(Merge pull request #\d+ from )[^/\s]+/(\S.*)$")


def public_subject(subject: str, authors: bool = False) -> str:
    """A commit subject as devkb stores it. `Merge pull request #N from owner/branch` names the head repository's
    owner, which is the author's (or their fork's) login, so unless `"github": {"authors": true}` it is stored as
    `Merge pull request #N from branch` (ADR-DEVKB-007 item 1). Git itself still holds the original."""
    if authors:
        return subject
    m = _MERGE_FROM.match(subject)
    return m.group(1) + m.group(2) if m else subject


@dataclass(frozen=True)
class Remote:
    host: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.host}/{self.owner}/{self.repo}"

    def web(self, kind: str, number: int) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}/{kind}/{number}"


_REMOTE = re.compile(r"^(?:[A-Za-z][\w+.-]*://)?(?:[^@/]+@)?([^/:@]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$")


def parse_remote(url: str) -> Remote | None:
    """host/owner/repo from any of the forms git accepts; a user name or token in the URL is discarded."""
    m = _REMOTE.match((url or "").strip())
    if not m:
        return None
    parts = [p for p in m.group(2).split("/") if p]
    if len(parts) != 2:
        return None
    return Remote(m.group(1).lower(), parts[0], parts[1])


def is_hosting(host: str, extra: str | None = None) -> bool:
    return "github" in host or (extra is not None and host == extra.lower())


def origin_remote(repo_root: Path, extra_host: str | None = None) -> Remote | None:
    """The `origin` remote when it is a GitHub host, else None: a repository without one gets no pull-request nodes."""
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(repo_root), capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    remote = parse_remote(out)
    return remote if remote and is_hosting(remote.host, extra_host) else None


# ── authentication and the real transport ─────────────────────────────────────────────────
def resolve_token(host: str) -> str | None:
    """GITHUB_TOKEN (github.com) or the enterprise variables, else the `gh` login for that host. A token is only ever
    sent to the host it was found for."""
    names: tuple[str, ...] = ("GITHUB_TOKEN", "GH_TOKEN") if host == "github.com" else ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
    if host != "github.com" and (os.environ.get("GH_HOST") == host or host in (os.environ.get("GITHUB_SERVER_URL") or "")):
        names += ("GITHUB_TOKEN", "GH_TOKEN")    # CI on that enterprise host (GitHub Actions sets GITHUB_SERVER_URL)
    for name in names:
        if os.environ.get(name):
            return os.environ[name].strip()
    try:
        r = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def api_url(host: str) -> str:
    return "https://api.github.com/graphql" if host == "github.com" else f"https://{host}/api/graphql"


def http_transport(host: str, token: str, timeout: float = 60.0) -> Transport:
    url = api_url(host)

    def send(query: str, variables: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps({"query": query, "variables": variables}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "devkb",
                     "GraphQL-Features": "issue_types,sub_issues"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode(errors="replace")[:300].lower()
            except OSError:
                pass
            if exc.code == 401:
                raise GitHubError("unauthorized", "the token was rejected (401)") from None
            if exc.code == 429 or (exc.code == 403 and ("rate limit" in body or exc.headers.get("x-ratelimit-remaining") == "0"
                                                        or exc.headers.get("retry-after"))):
                raise GitHubError("rate-limited", f"rate limited (HTTP {exc.code})") from None
            raise GitHubError("unreachable", f"HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            raise GitHubError("unreachable", f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from None
    return send


# ── queries ───────────────────────────────────────────────────────────────────────────────
_PR_COMMITS = "commits(first: 100%s) { totalCount pageInfo { hasNextPage endCursor } nodes { commit { oid } } }"
_PR_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: %(page)d, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title state mergedAt updatedAt baseRefName headRefName url
        mergeCommit { oid }
        labels(first: 30) { nodes { name } }
        closingIssuesReferences(first: 50) { nodes { number repository { nameWithOwner } } }
        %(commits)s
        %(author)s
      }
    }
  }
}"""
_PR_MORE_COMMITS = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) { %s }
  }
}""" % (_PR_COMMITS % ", after: $after")
_ISSUE_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(first: %(page)d, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title state createdAt closedAt updatedAt url
        labels(first: 30) { nodes { name } }
        milestone { title }
        %(extra)s
        %(author)s
      }
    }
  }
}"""
_ISSUE_EXTRA_FULL = "stateReason issueType { name } parent { number repository { nameWithOwner } } subIssues(first: 1) { totalCount }"
_ISSUE_EXTRA_BASIC = "stateReason"
_ISSUE_EXTRA_MIN = ""


def _author(authors: bool) -> str:
    return "author { login }" if authors else ""


def pr_query(authors: bool) -> str:
    return _PR_QUERY % {"page": PAGE, "commits": _PR_COMMITS % "", "author": _author(authors)}


def issue_query(authors: bool, extra: str) -> str:
    return _ISSUE_QUERY % {"page": PAGE, "extra": extra, "author": _author(authors)}


# ── normalising what comes back: the whitelist is the privacy rule ─────────────────────────
def _labels(node: dict) -> list[str]:
    return sorted({n.get("name") for n in ((node.get("labels") or {}).get("nodes") or []) if n and n.get("name")})


def _same_repo(ref: dict, repo_slug: str) -> bool:
    name = (ref.get("repository") or {}).get("nameWithOwner")
    return not name or not repo_slug or name.lower() == repo_slug.lower()


def _pr_record(node: dict, authors: bool, repo_slug: str = "") -> dict:
    state = str(node.get("state") or "").lower()
    rec = {
        "number": int(node["number"]), "title": node.get("title") or "", "state": state if state in ("open", "merged", "closed") else "closed",
        "merged_at": node.get("mergedAt"), "updated_at": node.get("updatedAt") or "", "base": node.get("baseRefName"),
        "head": node.get("headRefName"), "url": node.get("url"), "labels": _labels(node),
        "merge_commit": ((node.get("mergeCommit") or {}).get("oid")),
        # only this repository's issues: a reference to another repository's #N is not this repository's GH-N
        "closes": sorted({int(n["number"]) for n in ((node.get("closingIssuesReferences") or {}).get("nodes") or [])
                          if n and _same_repo(n, repo_slug)}),
        "commits": [c["commit"]["oid"] for c in ((node.get("commits") or {}).get("nodes") or []) if c and c.get("commit")],
        "commits_total": int((node.get("commits") or {}).get("totalCount") or 0),
    }
    if authors and (node.get("author") or {}).get("login"):
        rec["author"] = node["author"]["login"]
    return rec


def issue_type_from(issue_type: str | None, labels: list[str], has_children: bool) -> str:
    """ADR-DEVKB-007 item 2: the issue's type, else a label (bug, epic, enhancement/feature), else EPIC when it has
    sub-issues, else ISSUE. A typed issue keeps its type when it has sub-issues (a Bug with sub-issues stays a Bug);
    `has_sub_issues` is recorded beside it and the `epics` alias reads both."""
    if issue_type:
        return re.sub(r"[^A-Z0-9]+", "_", issue_type.upper()).strip("_") or "ISSUE"
    lower = {l.lower() for l in labels}
    if "epic" in lower:
        return "EPIC"
    if "bug" in lower:
        return "BUG"
    if lower & {"enhancement", "feature"}:
        return "FEATURE"
    return "EPIC" if has_children else "ISSUE"


def _issue_record(node: dict, authors: bool, repo_slug: str) -> dict:
    state = str(node.get("state") or "").lower()
    labels = _labels(node)
    parent = node.get("parent") or {}
    same_repo = (parent.get("repository") or {}).get("nameWithOwner", "").lower() in ("", repo_slug.lower())
    rec = {
        "number": int(node["number"]), "title": node.get("title") or "", "state": state if state in ("open", "closed") else "closed",
        "state_reason": (str(node["stateReason"]).lower() if node.get("stateReason") else None),
        "labels": labels, "milestone": (node.get("milestone") or {}).get("title"), "url": node.get("url"),
        "created_at": node.get("createdAt"), "closed_at": node.get("closedAt"), "updated_at": node.get("updatedAt") or "",
        "ticket_type": issue_type_from((node.get("issueType") or {}).get("name"), labels,
                                       int((node.get("subIssues") or {}).get("totalCount") or 0) > 0),
        "parent": int(parent["number"]) if parent.get("number") and same_repo else None,
        "has_sub_issues": int((node.get("subIssues") or {}).get("totalCount") or 0) > 0,
    }
    if authors and (node.get("author") or {}).get("login"):
        rec["author"] = node["author"]["login"]
    return rec


# ── the cache ────────────────────────────────────────────────────────────────────────────
class Cache:
    """One JSON file per kind. Holds only the normalised records above, so it cannot hold a description or review."""

    def __init__(self, directory: Path, remote: Remote, authors: bool) -> None:
        self.dir, self.remote, self.authors = directory, remote, authors

    def _path(self, kind: str) -> Path:
        return self.dir / f"{kind}.json"

    def load(self, kind: str) -> tuple[dict[int, dict], str, dict]:
        """(records by number, when they were fetched, listing state {"complete", "cursor"}). Empty when the cache is
        for another repository, another schema, or was written without the author logins now asked for."""
        try:
            data = json.loads(self._path(kind).read_text())
        except (OSError, ValueError):
            return {}, "", {}
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION or data.get("repo") != self.remote.slug:
            return {}, "", {}
        if self.authors and not data.get("authors"):
            return {}, "", {}
        items = {int(k): v for k, v in (data.get("items") or {}).items() if isinstance(v, dict)}
        if not self.authors:
            for v in items.values():
                v.pop("author", None)
        return items, str(data.get("fetched_at") or ""), {"complete": bool(data.get("complete")), "cursor": data.get("cursor")}

    def save(self, kind: str, items: dict[int, dict], complete: bool = True, cursor: str | None = None) -> None:
        clean = {str(n): ({k: v for k, v in rec.items() if self.authors or k != "author"}) for n, rec in sorted(items.items())}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._path(kind).write_text(json.dumps({
                "version": CACHE_VERSION, "repo": self.remote.slug, "authors": self.authors, "complete": complete, "cursor": cursor,
                "fetched_at": datetime.now(timezone.utc).isoformat(), "items": clean}, indent=0))
        except OSError:
            pass


# ── fetching ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Online:
    """What the online layer knows. `prs` and `issues` may hold cached records from an earlier build when a refresh
    failed; `report` says so."""
    prs: dict[int, dict] = field(default_factory=dict)
    issues: dict[int, dict] = field(default_factory=dict)
    report: dict = field(default_factory=dict)


def _gql(transport: Transport, query: str, variables: dict) -> dict:
    resp = transport(query, variables)
    errors = resp.get("errors")
    if errors or not isinstance(resp.get("data"), dict):
        text = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in (errors or []))[:300]
        kinds = " ".join(str(e.get("type", "")) for e in (errors or []) if isinstance(e, dict))
        if "RATE_LIMITED" in kinds or "rate limit" in text.lower():
            raise GitHubError("rate-limited", text or "rate limited")
        if "NOT_FOUND" in kinds:
            raise GitHubError("not-found", text or "repository not found or not visible to this token")
        if re.search(r"doesn't exist on type|Unknown type|Field '.*' doesn't exist", text):
            raise GitHubError("schema", text)
        if "bad credentials" in text.lower():
            raise GitHubError("unauthorized", text)
        raise GitHubError("graphql", text or "empty response")
    return resp["data"]


def _walk(transport: Transport, query: str, remote: Remote, connection: str, keep: Callable[[dict], dict],
          items: dict[int, dict], state: dict, save: Callable[[dict[int, dict], bool, str | None], None],
          finish: Callable[[dict], None] | None = None) -> tuple[dict[int, dict], int]:
    """Read one listing, newest-updated first, into `items`. Returns (records read, requests made); a GitHubError
    propagates after what was read is kept.

    A finished listing is refreshed incrementally: paging stops at records older than anything cached, and the cache
    is written only when that pass ends, because a partial pass would raise the "newest cached" mark over records not
    yet read. An unfinished listing (a first build, or one cut short) is resumed from its saved cursor and written
    after every page with `complete` false until the last page, so a repository too large for one rate-limit window
    is read across several builds instead of starting over each time."""
    resume = not state.get("complete")
    after = state.get("cursor") if resume else None
    newest = "" if resume else max((r.get("updated_at") or "" for r in items.values()), default="")
    fresh: dict[int, dict] = {}
    calls = 0
    while True:
        data = _gql(transport, query, {"owner": remote.owner, "name": remote.repo, "after": after})
        calls += 1
        conn = ((data.get("repository") or {}).get(connection)) or {}
        page: dict[int, dict] = {}
        stop = False
        for node in conn.get("nodes") or []:
            if not node:
                continue
            rec = keep(node)
            if newest and rec["updated_at"] and rec["updated_at"] < newest:
                stop = True
                continue
            page[rec["number"]] = rec
        for rec in page.values():
            if finish:
                finish(rec)
        fresh.update(page)
        info = conn.get("pageInfo") or {}
        more = bool(info.get("hasNextPage")) and not stop
        if resume:
            items.update(page)
            save(items, not more, info.get("endCursor") if more else None)
        if not more:
            if not resume:
                items.update(fresh)
                save(items, True, None)
            return fresh, calls
        after = info.get("endCursor")


def _more_commits(transport: Transport, remote: Remote, rec: dict) -> None:
    """A pull request with more than 100 commits: read the rest, up to the API's own cap. Raises GitHubError; the
    caller keeps the commits read so far, and `commits_total` then says the list is cut short."""
    after, pages = rec.pop("_after", None), 1
    while after and pages < MAX_COMMIT_PAGES:
        data = _gql(transport, _PR_MORE_COMMITS, {"owner": remote.owner, "name": remote.repo, "number": rec["number"], "after": after})
        conn = ((data.get("repository") or {}).get("pullRequest") or {}).get("commits") or {}
        rec["commits"] += [c["commit"]["oid"] for c in conn.get("nodes") or [] if c and c.get("commit")]
        info = conn.get("pageInfo") or {}
        after = info.get("endCursor") if info.get("hasNextPage") else None
        pages += 1


def fetch(remote: Remote, cache_dir: Path, authors: bool = False, transport: Transport | None = None) -> Online:
    """Fetch (or refresh from the cache) the repository's pull requests and issues. Never raises: the outcome is in
    `report`: status `ok`, `partial` (one kind failed), or `failed` (neither could be fetched), with the reason."""
    cache = Cache(cache_dir, remote, authors)
    out = Online()
    out.prs, pr_at, pr_state = cache.load("pull_requests")
    out.issues, is_at, is_state = cache.load("issues")
    report: dict = {"remote": remote.slug, "mode": "online", "authors": authors, "status": "ok", "reason": None,
                    "not_fetched": [], "requests": 0}
    if transport is None:
        token = resolve_token(remote.host)
        if not token:
            report.update(status="failed", reason="no GITHUB_TOKEN and no `gh` login for " + remote.host,
                          not_fetched=["pull_requests", "issues"], cached_from=_cached_note(pr_at, is_at))
            _describe(report, out, {"pull_requests": False, "issues": False})
            return out
        transport = http_transport(remote.host, token)

    ok = {"pull_requests": False, "issues": False}
    reasons: list[str] = []
    stale_cache = {k: bool(v) for k, v in (("pull_requests", out.prs), ("issues", out.issues))}

    slug = f"{remote.owner}/{remote.repo}"
    commits_cut: list[int] = []

    def keep_pr(node: dict) -> dict:
        rec = _pr_record(node, authors, slug)
        info = (node.get("commits") or {}).get("pageInfo") or {}
        if info.get("hasNextPage"):
            rec["_after"] = info.get("endCursor")
        return rec

    def finish_pr(rec: dict) -> None:
        """The rest of a long commit list; a failure here costs that one list, never the page."""
        try:
            _more_commits(transport, remote, rec)
        except GitHubError:
            commits_cut.append(rec["number"])
        rec.pop("_after", None)

    try:
        fresh, calls = _walk(transport, pr_query(authors), remote, "pullRequests", keep_pr, out.prs, pr_state,
                             lambda items, done, cursor: cache.save("pull_requests", items, done, cursor), finish_pr)
        report["requests"] += calls
        ok["pull_requests"] = True
        report["pull_requests_fetched"] = len(fresh)
    except GitHubError as exc:
        reasons.append(f"pull requests: {exc.kind}: {exc.message}")
        report["kind"] = exc.kind

    if commits_cut:
        report["commit_lists_not_fetched"] = sorted(commits_cut)[:50]
    last_error: GitHubError | None = None
    for extra in (_ISSUE_EXTRA_FULL, _ISSUE_EXTRA_BASIC, _ISSUE_EXTRA_MIN):
        try:
            fresh, calls = _walk(transport, issue_query(authors, extra), remote, "issues",
                                 lambda n: _issue_record(n, authors, slug), out.issues, is_state,
                                 lambda items, done, cursor: cache.save("issues", items, done, cursor))
            report["requests"] += calls
            ok["issues"] = True
            report["issues_fetched"] = len(fresh)
            report["issue_fields"] = "full" if extra == _ISSUE_EXTRA_FULL else "basic"
            last_error = None
            break
        except GitHubError as exc:        # a host without issue types or sub-issues: ask for less, not for nothing
            last_error = exc
            if exc.kind != "schema":
                break
    if last_error is not None:
        reasons.append(f"issues: {last_error.kind}: {last_error.message}")
        report.setdefault("kind", last_error.kind)

    report["listing_incomplete"] = [k for k in ("pull_requests", "issues")
                                    if not Cache(cache_dir, remote, authors).load(k)[2].get("complete")]
    report["not_fetched"] = [k for k, v in ok.items() if not v]
    if not report["not_fetched"]:
        report["status"] = "ok"
    else:
        report["status"] = "partial" if any(ok.values()) else "failed"
        report["reason"] = "; ".join(reasons)
        report["stale_cache_used"] = [k for k in report["not_fetched"] if stale_cache[k]]
        report["cached_from"] = _cached_note(pr_at, is_at)
    _describe(report, out, ok)
    out.report = report
    return out


def _cached_note(pr_at: str, is_at: str) -> dict:
    return {k: v for k, v in (("pull_requests", pr_at), ("issues", is_at)) if v}


def _describe(report: dict, out: Online, ok: dict[str, bool]) -> None:
    report["pull_requests"] = {"count": len(out.prs), "fresh": ok["pull_requests"]}
    report["issues"] = {"count": len(out.issues), "fresh": ok["issues"]}
    truncated = sorted(n for n, r in out.prs.items() if r.get("commits_total", 0) > len(r.get("commits", [])))
    if truncated:
        report["commit_lists_truncated"] = truncated[:50]
    # callers read the report from the returned object; keep it on `out` even on the early return
    out.report = report
