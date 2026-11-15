"""The opt-in online layer: read pull requests and issues from the GitHub API (ADR-DEVKB-007 §6).

Never reached unless the build is asked to (`devkb build --github`, or `{"github": {"enabled": true}}` in devkb.json).
Everything fetched is reduced on arrival to the fields the graph keeps, so a description, a review comment or an
author login is never held past the response (and never written to `.devkb/github/`, the local cache) unless the
repository set `"github": {"authors": true}` -- and then only the login.

Failure is data, not an exception: the client records what it could not fetch in `Status`, the build completes with
the offline layer, and the answers' coverage says so.
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

PER_PAGE = 100
GRAPHQL_BATCH = 25
TIMEOUT = 20

#: transport(method, url, headers, body_or_None) -> (status, response_headers, parsed_json). Tests replace it.
Transport = Callable[[str, str, dict, "bytes | None"], "tuple[int, dict, Any]"]


class FetchError(Exception):
    """One request failed; `kind` is `unreachable`, `rate-limited` or `refused` (auth, missing, forbidden)."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail = kind, detail


@dataclass
class Remote:
    host: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def web(self) -> str:
        return f"https://{self.host}/{self.slug}"

    @property
    def api(self) -> str:
        return "https://api.github.com" if self.host == "github.com" else f"https://{self.host}/api/v3"

    @property
    def graphql(self) -> str:
        return "https://api.github.com/graphql" if self.host == "github.com" else f"https://{self.host}/api/graphql"


_URL = re.compile(r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?|[^@/\s]+@)(?P<host>[^/:]+)(?::\d+)?[/:](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


def parse_remote(url: str) -> Remote | None:
    """host/owner/repo from a remote URL (https, ssh or scp-like); None for a local path or anything else."""
    m = _URL.match((url or "").strip())
    return Remote(m["host"].lower(), m["owner"], m["repo"]) if m else None


def origin_remote(repo_root: Path) -> Remote | None:
    """The repository's hosting remote: `origin`, else the first remote that parses. Reads git config only."""
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=str(repo_root), capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
    names = run("remote").split()
    for name in sorted(names, key=lambda n: n != "origin"):
        r = parse_remote(run("remote", "get-url", name).strip())
        if r:
            return r
    return None


def find_token(host: str = "github.com") -> str | None:
    """GITHUB_TOKEN, else the `gh` command-line tool's login. Only called once the online layer was asked for."""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    try:
        r = subprocess.run(["gh", "auth", "token", "--hostname", host], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (https URL built from the remote)
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"null")
        except ValueError:
            payload = None
        return exc.code, dict(exc.headers or {}), payload
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        raise FetchError("unreachable", str(getattr(exc, "reason", exc))) from exc


@dataclass
class Status:
    """What the online layer did, written to `.devkb/github/status.json` and the manifest."""
    enabled: bool = False
    repo: str = ""
    complete: bool = False
    requests: int = 0
    notes: list[str] = field(default_factory=list)       # one line per thing that could not be fetched
    unfetched_pulls: list[int] = field(default_factory=list)
    issues_complete: bool = False
    pulls_complete: bool = False
    from_cache: bool = False                            # answers used cached data the API could not refresh

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "repo": self.repo, "complete": self.complete, "requests": self.requests,
                "pulls_complete": self.pulls_complete, "issues_complete": self.issues_complete,
                "from_cache": self.from_cache, "unfetched_pulls": self.unfetched_pulls[:50],
                "n_unfetched_pulls": len(self.unfetched_pulls), "notes": self.notes[:20]}


class Client:
    def __init__(self, remote: Remote, token: str | None = None, transport: Transport | None = None) -> None:
        self.remote, self.token = remote, token
        self._transport = transport or _urllib_transport
        self.requests = 0

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "devkb"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _call(self, method: str, url: str, body: bytes | None = None) -> Any:
        self.requests += 1
        status, headers, payload = self._transport(method, url, self._headers(), body)
        low = {k.lower(): v for k, v in (headers or {}).items()}
        if status in (403, 429) and (low.get("x-ratelimit-remaining") == "0" or status == 429 or "retry-after" in low
                                      or "rate limit" in json.dumps(payload or {}).lower()):
            raise FetchError("rate-limited", f"HTTP {status}, resets at {low.get('x-ratelimit-reset', 'unknown')}")
        if status >= 400:
            raise FetchError("refused", f"HTTP {status} for {url.split('?')[0].replace(self.remote.api, '')}")
        return payload

    def get(self, path: str, **params: Any) -> Any:
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return self._call("GET", f"{self.remote.api}{path}" + (f"?{q}" if q else ""))

    def pages(self, path: str, **params: Any) -> list:
        """Every item of a paginated list, `per_page` at a time."""
        out: list = []
        page = 1
        while True:
            chunk = self.get(path, per_page=PER_PAGE, page=page, **params)
            if not isinstance(chunk, list):
                raise FetchError("refused", f"unexpected reply for {path}")
            out.extend(chunk)
            if len(chunk) < PER_PAGE:
                return out
            page += 1

    def closing_issues(self, numbers: list[int]) -> dict[int, list[int]]:
        """GitHub's own record of the issues each pull request closes (GraphQL `closingIssuesReferences`)."""
        out: dict[int, list[int]] = {}
        for i in range(0, len(numbers), GRAPHQL_BATCH):
            batch = numbers[i:i + GRAPHQL_BATCH]
            fields = " ".join(f"p{n}: pullRequest(number: {n}) {{ closingIssuesReferences(first: 50) {{ nodes {{ number repository {{ nameWithOwner }} }} }} }}"
                              for n in batch)
            query = f'query {{ repository(owner: "{self.remote.owner}", name: "{self.remote.repo}") {{ {fields} }} }}'
            reply = self._call("POST", self.remote.graphql, json.dumps({"query": query}).encode())
            repo = ((reply or {}).get("data") or {}).get("repository") or {}
            if not repo:
                raise FetchError("refused", "GraphQL reply had no repository")
            for n in batch:
                pr = repo.get(f"p{n}")
                if pr is not None:
                    out[n] = sorted(x["number"] for x in pr["closingIssuesReferences"]["nodes"]
                                    if ((x.get("repository") or {}).get("nameWithOwner") or self.remote.slug).lower()
                                    == self.remote.slug.lower())      # an issue of another repository is not ours
        return out


# ── reducing responses to what the graph keeps ───────────────────────────────────────────────────────────
def reduce_pull(raw: dict, authors: bool) -> dict:
    """The kept fields of one pull request. The description (`body`), reviewers and comments are never read."""
    out = {"number": raw["number"], "title": raw.get("title") or "", "updated_at": raw.get("updated_at") or "",
           "state": "merged" if raw.get("merged_at") else ("open" if raw.get("state") == "open" else "closed"),
           "merged_at": raw.get("merged_at"), "base": (raw.get("base") or {}).get("ref"),
           "head": (raw.get("head") or {}).get("ref"), "labels": sorted(lb.get("name", "") for lb in raw.get("labels") or []),
           "url": raw.get("html_url"), "merge_commit_sha": raw.get("merge_commit_sha")}
    if authors:
        out["author"] = (raw.get("user") or {}).get("login")
    return out


def reduce_issue(raw: dict, authors: bool) -> dict:
    out = {"number": raw["number"], "title": raw.get("title") or "", "updated_at": raw.get("updated_at") or "",
           "state": raw.get("state"), "state_reason": raw.get("state_reason"),
           "labels": sorted((lb.get("name", "") if isinstance(lb, dict) else str(lb)) for lb in raw.get("labels") or []),
           "milestone": (raw.get("milestone") or {}).get("title"), "url": raw.get("html_url"),
           "created_at": raw.get("created_at"), "closed_at": raw.get("closed_at"),
           "type": (raw.get("type") or {}).get("name") if isinstance(raw.get("type"), dict) else None,
           "n_sub_issues": int((raw.get("sub_issues_summary") or {}).get("total") or 0),
           "parent": _number_from_url(raw.get("parent_issue_url"))}
    if authors:
        out["author"] = (raw.get("user") or {}).get("login")
    return out


def _number_from_url(url: str | None) -> int | None:
    m = re.search(r"/issues/(\d+)$", url or "")
    return int(m.group(1)) if m else None


# ── the local cache ─────────────────────────────────────────────────────────────────────────────────────
class Cache:
    """`.devkb/github/{pulls,issues}.json`: reduced items keyed by number, each with the `updated_at` it was fetched
    at. A cache written for another repository, or with another `authors` setting, is discarded: the setting decides
    what may be on disk."""

    def __init__(self, directory: Path, repo: str, authors: bool) -> None:
        self.dir, self.repo, self.authors = directory, repo, authors
        self.pulls = self._load("pulls.json")
        self.issues = self._load("issues.json")

    def _load(self, name: str) -> dict[str, dict]:
        try:
            data = json.loads((self.dir / name).read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("repo") != self.repo or bool(data.get("authors")) != self.authors:
            return {}
        return data.get("items") or {}

    def save(self, status: Status) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, items in (("pulls.json", self.pulls), ("issues.json", self.issues)):
            (self.dir / name).write_text(json.dumps({"repo": self.repo, "authors": self.authors, "items": items},
                                                    sort_keys=True))
        (self.dir / "status.json").write_text(json.dumps(status.to_dict(), indent=2))


@dataclass
class Fetched:
    pulls: dict[int, dict]            # number -> reduced pull request, with "commits" [{sha, subject}] and "closes" [n]
    issues: dict[int, dict]           # number -> reduced issue, with "sub_issues" [n]
    status: Status


def fetch(client: Client, cache_dir: Path, authors: bool) -> Fetched:
    """Pull requests and issues of the repository, fetching only what changed since the cache. Never raises on an
    unreachable or rate-limited API: it returns what it has and says what is missing."""
    st = Status(enabled=True, repo=client.remote.slug)
    cache = Cache(cache_dir, client.remote.slug, authors)
    pulls: dict[int, dict] = {}
    issues: dict[int, dict] = {}

    # pull requests
    try:
        listing = client.pages(f"/repos/{client.remote.slug}/pulls", state="all", sort="updated", direction="desc")
        st.pulls_complete = True
    except FetchError as exc:
        listing = None
        st.notes.append(f"pull requests not listed ({exc})")
    if listing is None:
        st.from_cache = bool(cache.pulls)
        pulls = {int(n): v for n, v in cache.pulls.items()}
    else:
        todo: list[dict] = []
        for raw in listing:
            item = reduce_pull(raw, authors)
            old = cache.pulls.get(str(item["number"]))
            if old and old.get("updated_at") == item["updated_at"] and "commits" in old and "closes" in old:
                pulls[item["number"]] = old
            else:
                todo.append(item)
        failed: list[int] = []
        for item in todo:
            try:
                commits = client.pages(f"/repos/{client.remote.slug}/pulls/{item['number']}/commits")
            except FetchError as exc:
                st.notes.append(f"commits of pull requests not fetched ({exc})")
                failed = [t["number"] for t in todo[todo.index(item):]]
                break
            item["commits"] = [{"sha": c["sha"], "subject": ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0]}
                               for c in commits]
            pulls[item["number"]] = item
        if not failed:
            fresh = [t["number"] for t in todo]
            try:
                closes = client.closing_issues(fresh)
                for n in fresh:
                    pulls[n]["closes"] = closes.get(n, [])
            except FetchError as exc:
                st.notes.append(f"closing references not fetched ({exc})")
                failed = fresh
        failed = sorted(set(failed) | {n for n, v in pulls.items() if "closes" not in v})
        for n in failed:
            pulls.pop(n, None)
            if str(n) in cache.pulls:                     # an older cached copy is better than nothing
                pulls[n] = cache.pulls[str(n)]
                st.from_cache = True
        st.unfetched_pulls = sorted(failed)
        if failed:
            st.pulls_complete = False
        cache.pulls = {str(n): v for n, v in pulls.items()}

    # issues
    try:
        raw_issues = client.pages(f"/repos/{client.remote.slug}/issues", state="all", sort="updated", direction="desc")
        st.issues_complete = True
    except FetchError as exc:
        raw_issues = None
        st.notes.append(f"issues not listed ({exc})")
    if raw_issues is None:
        st.from_cache = st.from_cache or bool(cache.issues)
        issues = {int(n): v for n, v in cache.issues.items()}
    else:
        for raw in raw_issues:
            if "pull_request" in raw:                      # the issues list also returns pull requests
                continue
            item = reduce_issue(raw, authors)
            old = cache.issues.get(str(item["number"]))
            if old and old.get("updated_at") == item["updated_at"] and "sub_issues" in old:
                issues[item["number"]] = old
                continue
            item["sub_issues"] = []
            if item["n_sub_issues"]:
                try:
                    subs = client.pages(f"/repos/{client.remote.slug}/issues/{item['number']}/sub_issues")
                    item["sub_issues"] = sorted(s["number"] for s in subs)
                except FetchError as exc:
                    st.notes.append(f"sub-issues of #{item['number']} not fetched ({exc})")
                    st.issues_complete = False
                    # not cached without them: the next build tries again
                    issues[item["number"]] = {**item, "updated_at": ""}
                    continue
            issues[item["number"]] = item
        cache.issues = {str(n): v for n, v in issues.items()}

    st.complete = st.pulls_complete and st.issues_complete
    st.requests = client.requests
    cache.save(st)
    return Fetched(pulls, issues, st)


def make_client(repo_root: Path, remote: Remote | None = None) -> Client | None:
    """A client for the repository's remote with whatever authentication exists, or None when it has no hosting
    remote. Looking for a token may run `gh`; this is only called when the online layer was asked for."""
    remote = remote or origin_remote(repo_root)
    if remote is None:
        return None
    return Client(remote, find_token(remote.host))
