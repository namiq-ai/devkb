"""ADR-DEVKB-007: pull requests and hosted issues. Fixture git repositories only; the GitHub API is a fake and no test
here opens a socket."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build as build_mod, build_symbols, github, packs, process_api  # noqa: E402
from devkb.extractors import pull_requests  # noqa: E402
from devkb.model import uid_for  # noqa: E402

REMOTE = "https://ci-user:s3cr3t-token@github.com/acme/widgets.git"
LOGIN = "octocat-secret-login"
EMAIL = "octo@example.org"
BODY = "DESCRIPTION-TEXT-with-api-key-AKIA1234567890"
REVIEW = "REVIEW-COMMENT-TEXT-please-rename"

APP_V1 = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
APP_V2 = APP_V1 + "\n\ndef gamma():\n    return alpha() + 3\n"
APP_V3 = APP_V2.replace("return alpha() + 3", "return alpha() + 4")
APP_V4 = APP_V3.replace("return 2", "return 22")
TEST = "from app import alpha, gamma\n\n\ndef test_alpha():\n    assert alpha() == 1\n\n\ndef test_gamma():\n    assert gamma() == 5\n"


def git(root: Path, *args: str, env: dict | None = None) -> str:
    full = {**os.environ, "GIT_AUTHOR_NAME": "Dev One", "GIT_AUTHOR_EMAIL": "dev1@example.invalid",
            "GIT_COMMITTER_NAME": "Dev One", "GIT_COMMITTER_EMAIL": "dev1@example.invalid", **(env or {})}
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=full).stdout.strip()


def commit(root: Path, files: dict[str, str], message: str, *extra: str) -> str:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message, *extra)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """master: initial; PR 5 merged with a merge commit (two commits on a branch); PR 6 squashed (closing keyword in
    the body); a direct commit mentioning #7; PR 9 merged with a body that says `Fixes #5`, a pull request."""
    monkeypatch.delenv("DEVKB_DIR", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    root = tmp_path / "widgets"
    root.mkdir()
    git(root, "init", "-q", "-b", "master")
    git(root, "remote", "add", "origin", REMOTE)
    s = {"base": commit(root, {"app.py": APP_V1, "tests/test_app.py": TEST}, "initial")}
    git(root, "checkout", "-q", "-b", "feature/x")
    s["b1"] = commit(root, {"app.py": APP_V2}, "add gamma")
    s["b2"] = commit(root, {"app.py": APP_V3}, "tune gamma", "-m", "Fixes #7 and resolves #8")
    git(root, "checkout", "-q", "master")
    s["merge"] = (git(root, "merge", "--no-ff", "-q", "feature/x", "-m", "Merge pull request #5 from alice-fork/feature/x",
                      "-m", "Add gamma"), git(root, "rev-parse", "HEAD"))[1]
    s["squash"] = commit(root, {"app.py": APP_V4}, "Speed up beta (#6)", "-m", "Closes #8\n\n* speed up\n* Co-authored-by: A <a@example.invalid>")
    s["mention"] = commit(root, {"notes.txt": "n\n"}, "docs: see #7 for background")
    s["pr9"] = commit(root, {"notes.txt": "n2\n"}, "Tidy notes (#9)", "-m", "Fixes #5")
    return root, s


def build_graph(root: Path, **kw):
    build_symbols.build(str(root))
    graph, devkb_dir = build_mod.build(str(root), **kw)
    return graph, devkb_dir


def node(graph, typ, key):
    return next((n for n in graph.nodes(typ) if n.natural_key == key), None)


def edges(graph, verb):
    return {(e.src, e.dst): e for e in graph.edges(verb)}


# ── the fake GitHub ──────────────────────────────────────────────────────────────────────
class FakeGitHub:
    """Answers the two listing queries and the commit-continuation query from tables, and returns what a careless
    server would: descriptions, review text, author logins and e-mail, in every node, whether asked or not."""

    def __init__(self, shas: dict[str, str], page: int = 100) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail: GithubFail | None = None
        self.schema_older = False
        sha = shas
        noise = {"body": BODY, "bodyText": BODY, "author": {"login": LOGIN, "email": EMAIL},
                 "reviews": {"nodes": [{"body": REVIEW, "author": {"login": LOGIN}}]}, "email": EMAIL}
        self.prs = [
            {"number": 5, "title": "Add gamma", "state": "MERGED", "mergedAt": "2026-05-02T10:00:00Z", "updatedAt": "2026-05-02T10:00:00Z",
             "baseRefName": "master", "headRefName": "feature/x", "url": "https://github.com/acme/widgets/pull/5",
             "mergeCommit": {"oid": sha["merge"]}, "labels": {"nodes": [{"name": "enhancement"}]},
             "closingIssuesReferences": {"nodes": [{"number": 7}]},
             "commits": {"totalCount": 2, "pageInfo": {"hasNextPage": False, "endCursor": None},
                         "nodes": [{"commit": {"oid": sha["b1"]}}, {"commit": {"oid": sha["b2"]}}]}, **noise},
            {"number": 6, "title": "Speed up beta", "state": "MERGED", "mergedAt": "2026-05-03T10:00:00Z", "updatedAt": "2026-05-03T10:00:00Z",
             "baseRefName": "master", "headRefName": "perf", "url": "https://github.com/acme/widgets/pull/6",
             "mergeCommit": {"oid": sha["squash"]}, "labels": {"nodes": []},
             # GitHub's own record: this pull request closes nothing (the keyword was in a quoted line)
             "closingIssuesReferences": {"nodes": []},
             "commits": {"totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"commit": {"oid": "f" * 40}}]}, **noise},
            {"number": 9, "title": "Tidy notes", "state": "MERGED", "mergedAt": "2026-05-04T10:00:00Z", "updatedAt": "2026-05-04T10:00:00Z",
             "baseRefName": "master", "headRefName": "notes", "url": "https://github.com/acme/widgets/pull/9",
             "mergeCommit": {"oid": sha["pr9"]}, "labels": {"nodes": []}, "closingIssuesReferences": {"nodes": []},
             "commits": {"totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"commit": {"oid": sha["pr9"]}}]}, **noise},
            {"number": 11, "title": "Open work", "state": "OPEN", "mergedAt": None, "updatedAt": "2026-05-05T10:00:00Z",
             "baseRefName": "master", "headRefName": "wip", "url": "https://github.com/acme/widgets/pull/11",
             "mergeCommit": None, "labels": {"nodes": []}, "closingIssuesReferences": {"nodes": [{"number": 8}]},
             "commits": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}, **noise},
        ]
        self.issues = [
            {"number": 8, "title": "Beta is slow", "state": "CLOSED", "stateReason": "COMPLETED", "createdAt": "2026-04-01T00:00:00Z",
             "closedAt": "2026-05-03T10:00:00Z", "updatedAt": "2026-05-03T10:00:00Z", "url": "https://github.com/acme/widgets/issues/8",
             "labels": {"nodes": [{"name": "bug"}]}, "milestone": {"title": "v1"}, "issueType": None,
             "parent": {"number": 10, "repository": {"nameWithOwner": "acme/widgets"}}, "subIssues": {"totalCount": 0}, **noise},
            {"number": 7, "title": "Gamma is missing", "state": "CLOSED", "stateReason": "COMPLETED", "createdAt": "2026-04-02T00:00:00Z",
             "closedAt": "2026-05-02T10:00:00Z", "updatedAt": "2026-05-02T10:00:00Z", "url": "https://github.com/acme/widgets/issues/7",
             "labels": {"nodes": [{"name": "enhancement"}]}, "milestone": None, "issueType": {"name": "Feature"},
             "parent": None, "subIssues": {"totalCount": 0}, **noise},
            {"number": 10, "title": "Performance", "state": "OPEN", "stateReason": None, "createdAt": "2026-03-01T00:00:00Z",
             "closedAt": None, "updatedAt": "2026-03-01T00:00:00Z", "url": "https://github.com/acme/widgets/issues/10",
             "labels": {"nodes": []}, "milestone": None, "issueType": None, "parent": None, "subIssues": {"totalCount": 1}, **noise},
        ]

    def __call__(self, query: str, variables: dict) -> dict:
        self.calls.append((query, dict(variables)))
        if self.fail:
            raise github.GitHubError(self.fail.kind, self.fail.message)
        if "pullRequests(" in query:
            return {"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.prs}}}}
        if "issues(" in query:
            if self.schema_older and "issueType" in query:
                return {"errors": [{"message": "Field 'issueType' doesn't exist on type 'Issue'"}]}
            return {"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.issues}}}}
        raise AssertionError("unexpected query")


class GithubFail:
    def __init__(self, kind: str, message: str) -> None:
        self.kind, self.message = kind, message


# ── offline ──────────────────────────────────────────────────────────────────────────────
def test_offline_layer_finds_merge_and_squash_pull_requests_with_the_adr_confidences(repo):
    root, s = repo
    graph, _ = build_graph(root)
    pr5, pr6 = node(graph, "PullRequest", "PR-5"), node(graph, "PullRequest", "PR-6")
    assert pr5.props["number"] == 5 and pr5.props["state"] == "merged" and pr5.props["merge_style"] == "merge"
    assert pr5.props["title"] == "Add gamma"
    assert pr5.props["head"] == "feature/x", "the owner of `owner/branch` is a login and is dropped"
    assert pr5.props["url"] == "https://github.com/acme/widgets/pull/5"
    assert pr6.props["merge_style"] == "squash" and pr6.props["title"] == "Speed up beta"
    merges = edges(graph, "MERGES")
    assert {dst for (src, dst) in merges if src == "PR-5"} == {s["merge"], s["b1"], s["b2"]}, "the merge commit and what it brought in"
    assert {dst for (src, dst) in merges if src == "PR-6"} == {s["squash"]}
    assert all(e.confidence == 0.9 for e in merges.values())
    assert {e.source for (src, _), e in merges.items() if src == "PR-5"} == {"git-merge-subject"}
    assert {e.source for (src, _), e in merges.items() if src == "PR-6"} == {"git-squash-subject"}
    assert node(graph, "PullRequest", "PR-9") is not None


def test_offline_closing_keywords_give_unverified_closes_at_0_7_and_never_point_at_a_pull_request(repo):
    root, s = repo
    graph, _ = build_graph(root)
    closes = edges(graph, "CLOSES")
    assert set(closes) == {("PR-5", "GH-7"), ("PR-5", "GH-8"), ("PR-6", "GH-8")}, "`Fixes #5` in PR 9 names a pull request"
    for e in closes.values():
        assert e.confidence == 0.7 and e.source == "git-closing-keyword" and e.extra == {"unverified": True}
    assert node(graph, "Ticket", "GH-8").props["unverified"] is True
    assert node(graph, "Ticket", "GH-5") is None, "an issue GH-5 and a pull request PR-5 never both exist"


def test_offline_bare_hash_mentions_make_no_edge(repo):
    root, s = repo
    graph, _ = build_graph(root)
    assert not [e for e in graph.edges("REFERENCES") if e.dst.startswith("GH-")]


def test_a_repository_without_a_github_remote_gets_no_new_nodes(repo):
    root, _ = repo
    git(root, "remote", "set-url", "origin", "https://gitlab.com/acme/widgets.git")
    graph, devkb_dir = build_graph(root)
    assert not list(graph.nodes("PullRequest")) and not list(graph.edges("MERGES")) and not list(graph.edges("CLOSES"))
    assert "github" not in json.loads((devkb_dir / "manifest.json").read_text())


def test_remote_parsing_drops_credentials_and_accepts_every_git_form():
    for url in ("git@github.com:acme/widgets.git", "ssh://git@github.com/acme/widgets", "https://u:tok@github.com/acme/widgets.git",
                "https://github.com/acme/widgets/"):
        r = github.parse_remote(url)
        assert (r.host, r.owner, r.repo) == ("github.com", "acme", "widgets"), url
    assert github.parse_remote("not a url") is None


# ── no network by default ────────────────────────────────────────────────────────────────
def test_default_build_makes_no_request_and_reads_no_token(repo, monkeypatch):
    root, _ = repo

    def boom(*a, **k):
        raise AssertionError("the network was touched")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(github, "http_transport", boom)
    monkeypatch.setattr(github, "resolve_token", boom)
    monkeypatch.setenv("GITHUB_TOKEN", "would-be-used-if-asked")
    graph, devkb_dir = build_graph(root)
    manifest = json.loads((devkb_dir / "manifest.json").read_text())
    assert manifest["github"]["mode"] == "offline" and manifest["github"]["status"] == "offline"
    assert not (devkb_dir / "github").exists()


def test_enabling_in_devkb_json_turns_the_online_layer_on_and_no_github_overrides_it(repo):
    root, s = repo
    (root / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    assert github.settings(root).enabled and not github.settings(root, False).enabled and github.settings(root, True).enabled
    fake = FakeGitHub(s)
    build_graph(root, github=False, github_transport=fake)
    assert fake.calls == []
    build_graph(root, github_transport=fake)
    assert fake.calls


# ── online ───────────────────────────────────────────────────────────────────────────────
def test_online_layer_replaces_guesses_with_githubs_record(repo):
    root, s = repo
    fake = FakeGitHub(s)
    graph, devkb_dir = build_graph(root, github=True, github_transport=fake)
    merges = edges(graph, "MERGES")
    assert merges[("PR-5", s["b1"])].confidence == 1.0 and merges[("PR-5", s["merge"])].confidence == 1.0
    assert merges[("PR-5", s["b1"])].source == "github-pr-commits"
    assert not [k for k in merges if k[0] == "PR-11"], "an open pull request has merged nothing"
    closes = edges(graph, "CLOSES")
    assert closes[("PR-5", "GH-7")].confidence == 1.0 and closes[("PR-5", "GH-7")].source == "github-closing-reference"
    assert ("PR-5", "GH-8") not in closes and ("PR-6", "GH-8") not in closes, "the offline keyword edges the API contradicts are gone"
    assert ("PR-11", "GH-8") in closes
    assert all(not e.extra.get("unverified") for e in closes.values())
    assert node(graph, "PullRequest", "PR-5").props["base"] == "master"
    assert node(graph, "PullRequest", "PR-5").props["labels"] == ["enhancement"]
    assert node(graph, "PullRequest", "PR-11").props["state"] == "open"
    assert node(graph, "Ticket", "GH-8").props.get("unverified") is None
    manifest = json.loads((devkb_dir / "manifest.json").read_text())
    assert manifest["github"]["status"] == "ok" and manifest["github"]["mode"] == "online"


def test_hosted_issues_are_tickets_with_types_children_and_mentions(repo):
    root, s = repo
    graph, _ = build_graph(root, github=True, github_transport=FakeGitHub(s))
    t7, t8, t10 = (node(graph, "Ticket", f"GH-{n}") for n in (7, 8, 10))
    assert t7.source == "github-issues" and t7.props["ticket_type"] == "FEATURE", "the issue type wins over labels"
    assert t8.props["ticket_type"] == "BUG", "no issue type: the `bug` label"
    assert t10.props["ticket_type"] == "EPIC", "an issue with sub-issues is an epic"
    assert t8.props["state"] == "closed" and t8.props["state_reason"] == "completed" and t8.props["milestone"] == "v1"
    assert t8.props["labels"] == ["bug"] and t8.props["url"].endswith("/issues/8") and t8.props["closed_at"]
    child = edges(graph, "CHILD_OF")
    assert child[("GH-8", "GH-10")].source == "github-sub-issues" and child[("GH-8", "GH-10")].confidence == 1.0
    refs = {k: e for k, e in edges(graph, "REFERENCES").items() if k[1].startswith("GH-")}
    assert refs[(s["mention"], "GH-7")].source == "git-hash-mention" and refs[(s["mention"], "GH-7")].confidence == 0.8
    assert not [k for k in refs if k[1] == "GH-5" or k[1] == "GH-6" or k[1] == "GH-9"], "pull requests are not issues"


def test_labels_decide_the_ticket_type_when_there_is_no_issue_type():
    t = github.issue_type_from
    assert (t(None, ["Bug"], False), t(None, ["epic"], False), t(None, ["enhancement"], False), t(None, ["feature"], False),
            t(None, ["docs"], False), t("Task", ["bug"], False), t("Bug", [], True), t(None, [], True)) == \
        ("BUG", "EPIC", "FEATURE", "FEATURE", "ISSUE", "TASK", "BUG", "EPIC"), "a typed issue keeps its type; sub-issues alone make an epic"


def test_a_host_without_issue_types_gets_a_reduced_query(repo):
    root, s = repo
    fake = FakeGitHub(s)
    fake.schema_older = True
    graph, devkb_dir = build_graph(root, github=True, github_transport=fake)
    assert node(graph, "Ticket", "GH-8").props["ticket_type"] == "BUG"
    assert json.loads((devkb_dir / "manifest.json").read_text())["github"]["issue_fields"] == "basic"


def test_the_cache_is_keyed_by_updated_at_so_a_rebuild_fetches_only_what_changed(repo):
    root, s = repo
    fake = FakeGitHub(s)
    _, devkb_dir = build_graph(root, github=True, github_transport=fake)
    cache = devkb_dir / "github"
    assert (cache / "pull_requests.json").is_file() and (cache / "issues.json").is_file()
    first = len(fake.calls)

    class Newer(FakeGitHub):
        def __call__(self, query, variables):
            self.calls.append((query, dict(variables)))
            if "pullRequests(" in query:
                changed = [dict(p) for p in self.prs if p["number"] in (11, 9)]
                next(p for p in changed if p["number"] == 11)["title"] = "Open work, renamed"
                return {"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": changed}}}}
            return {"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}}

    newer = Newer(s)
    graph, _ = build_graph(root, github=True, github_transport=newer)
    assert first == 2 and len(newer.calls) == 2
    assert node(graph, "PullRequest", "PR-5").props["labels"] == ["enhancement"], "unchanged records come from the cache"
    assert node(graph, "Ticket", "GH-7") is not None, "so do issues"
    assert node(graph, "PullRequest", "PR-11").props["title"] == "Open work, renamed", "a changed record replaces the cached one"
    assert node(graph, "PullRequest", "PR-9").props["title"] == "Tidy notes"


def test_long_pull_requests_get_their_remaining_commits(repo):
    root, s = repo
    fake = FakeGitHub(s)
    fake.prs[0]["commits"] = {"totalCount": 2, "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                              "nodes": [{"commit": {"oid": s["b1"]}}]}
    base_call = fake.__call__

    def with_more(query, variables):
        if "pullRequest(number" in query:
            return {"data": {"repository": {"pullRequest": {"commits": {"totalCount": 2, "pageInfo": {"hasNextPage": False, "endCursor": None},
                                                                       "nodes": [{"commit": {"oid": s["b2"]}}]}}}}}
        return base_call(query, variables)

    graph, _ = build_graph(root, github=True, github_transport=with_more)
    assert edges(graph, "MERGES")[("PR-5", s["b2"])].confidence == 1.0


# ── when GitHub cannot be reached ────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", ["unreachable", "rate-limited", "unauthorized"])
def test_unreachable_api_completes_the_build_with_the_offline_layer_and_says_so(repo, kind, capsys):
    root, s = repo
    fake = FakeGitHub(s)
    fake.fail = GithubFail(kind, f"simulated {kind}")
    graph, devkb_dir = build_graph(root, github=True, github_transport=fake)
    assert node(graph, "PullRequest", "PR-5").props["merge_style"] == "merge"
    assert edges(graph, "MERGES")[("PR-5", s["b1"])].confidence == 0.9
    assert edges(graph, "CLOSES")[("PR-5", "GH-7")].extra == {"unverified": True}
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["status"] == "failed" and kind in report["reason"] and report["not_fetched"] == ["pull_requests", "issues"]
    assert "github layer failed" in capsys.readouterr().err

    api = process_api.ProcessAPI(str(root), telemetry=False)
    cov = api.call("lineage", ticket="GH-7")["coverage"]
    assert cov["complete"] is False and cov["github"] == "failed" and "pull_requests" in cov["note"] and cov["unverified"] == ["PR-5"]


def test_a_failed_refresh_falls_back_to_the_cache_and_says_it_did(repo):
    root, s = repo
    build_graph(root, github=True, github_transport=FakeGitHub(s))
    down = FakeGitHub(s)
    down.fail = GithubFail("rate-limited", "slow down")
    graph, devkb_dir = build_graph(root, github=True, github_transport=down)
    assert edges(graph, "MERGES")[("PR-5", s["b1"])].confidence == 1.0, "cached GitHub data still beats the guess"
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["status"] == "failed" and report["stale_cache_used"] == ["pull_requests", "issues"]
    note = process_api.ProcessAPI(str(root), telemetry=False).call("lineage", ticket="GH-7")["coverage"]["note"]
    assert "cached data" in note


def test_no_token_and_no_gh_login_is_reported_not_raised(repo, monkeypatch):
    root, _ = repo
    monkeypatch.setattr(github, "resolve_token", lambda host: None)
    graph, devkb_dir = build_graph(root, github=True)
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["status"] == "failed" and "GITHUB_TOKEN" in report["reason"]
    assert node(graph, "PullRequest", "PR-5") is not None


def test_a_partial_failure_keeps_what_was_fetched(repo):
    root, s = repo
    fake = FakeGitHub(s)
    ok = fake.__call__

    def flaky(query, variables):
        if "issues(" in query:
            raise github.GitHubError("rate-limited", "issues ran out")
        return ok(query, variables)

    graph, devkb_dir = build_graph(root, github=True, github_transport=flaky)
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["status"] == "partial" and report["not_fetched"] == ["issues"]
    assert edges(graph, "CLOSES")[("PR-5", "GH-7")].confidence == 1.0


def test_graphql_errors_are_classified():
    def tr(resp):
        return lambda q, v: resp

    for resp, kind in (({"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}, "rate-limited"),
                       ({"errors": [{"type": "NOT_FOUND", "message": "Could not resolve"}]}, "not-found"),
                       ({"errors": [{"message": "Bad credentials"}]}, "unauthorized"), ({"data": None}, "graphql")):
        with pytest.raises(github.GitHubError) as exc:
            github._gql(tr(resp), "q", {})
        assert exc.value.kind == kind


# ── privacy ──────────────────────────────────────────────────────────────────────────────
def _everything_written(devkb_dir: Path, root: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in sorted(devkb_dir.rglob("*")) if p.is_file() and p.suffix in (".json", ".jsonl"))


SECRETS = (BODY, "AKIA1234567890", REVIEW, EMAIL, "s3cr3t-token", "ci-user")


def test_no_description_review_text_login_or_email_is_written_by_default(repo):
    root, s = repo
    fake = FakeGitHub(s)
    _, devkb_dir = build_graph(root, github=True, github_transport=fake)
    text = _everything_written(devkb_dir, root)
    for secret in (*SECRETS, LOGIN, "alice-fork"):
        assert secret not in text, secret
    asked = "\n".join(q for q, _ in fake.calls)
    assert "body" not in asked and "login" not in asked and "reviews" not in asked and "email" not in asked
    for n in ("PR-5", "PR-6"):
        assert "author" not in json.loads(next(l for l in (devkb_dir / "nodes.jsonl").read_text().splitlines()
                                              if json.loads(l)["uid"] == uid_for("PullRequest", n)))["properties"]


def test_authors_are_stored_only_when_opted_in(repo):
    root, s = repo
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    fake = FakeGitHub(s)
    graph, devkb_dir = build_graph(root, github=True, github_transport=fake)
    assert node(graph, "PullRequest", "PR-5").props["author"] == LOGIN and node(graph, "Ticket", "GH-7").props["author"] == LOGIN
    assert any("login" in q for q, _ in fake.calls)
    text = _everything_written(devkb_dir, root)
    for secret in (BODY, REVIEW, EMAIL):
        assert secret not in text, "authors opts in to the login only"
    # opting out again drops the logins from graph and cache
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": False}}))
    _, devkb_dir = build_graph(root, github=True, github_transport=FakeGitHub(s))
    assert LOGIN not in _everything_written(devkb_dir, root)


# ── tools and packs ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def online_api(repo):
    root, s = repo
    build_graph(root, github=True, github_transport=FakeGitHub(s))
    return process_api.ProcessAPI(str(root), telemetry=False), s, root


@pytest.fixture
def offline_api(repo):
    root, s = repo
    build_graph(root)
    return process_api.ProcessAPI(str(root), telemetry=False), s, root


def test_trace_and_lineage_follow_closes_and_merges(online_api):
    api, s, _ = online_api
    tr = api.call("trace", ticket="GH-7")
    assert tr["type"] == "FEATURE" and [p["id"] for p in tr["pull_requests"]] == ["PR-5"]
    assert tr["coverage"]["complete"] is True and tr["coverage"]["github"] == "ok"
    ln = api.call("lineage", ticket="GH-7")
    assert ln["commits"] == 4, "the merge commit, the two commits the pull request brought in, and the commit that mentions #7"
    assert ln["pull_requests"][0]["id"] == "PR-5"
    epic = api.call("lineage", ticket="GH-10")
    assert epic["sub_issues"] == ["GH-8"] and api.call("lineage", ticket="GH-8")["epic"] == ["GH-10"]
    assert api.call("trace", ticket="GH-10")["sub_issues"][0]["id"] == "GH-8"


def test_offline_answers_state_that_unverified_links_are_incomplete(offline_api):
    api, s, _ = offline_api
    ln = api.call("lineage", ticket="GH-7")
    assert ln["pull_requests"] == [{"id": "PR-5", "title": "Add gamma", "state": "merged", "merged_at": ln["pull_requests"][0]["merged_at"],
                                    "confidence": 0.7, "unverified": True}]
    cov = ln["coverage"]
    assert cov["complete"] is False and cov["github"] == "offline" and cov["unverified"] == ["PR-5"]
    assert "--github" in cov["note"]


def test_history_and_review_pack_name_the_pull_request(online_api):
    api, s, root = online_api
    h = api.call("history", files=["app.py"], limit=10)
    by_hash = {c["h"]: c for c in h["commits"]}
    assert by_hash[s["b1"][:8]]["pr"] == ["PR-5"] and by_hash[s["squash"][:8]]["pr"] == ["PR-6"]
    assert by_hash[s["b1"][:8]]["closes"] == ["GH-7"]
    assert h["coverage"]["github"] == "ok"
    r = api.call("review_pack", rev=s["b2"])
    assert [p["id"] for p in r["pull_requests"]] == ["PR-5"] and "GH-7" in r["tickets"]
    assert api.call("review_pack", rev=f"{s['base']}..{s['merge']}")["pull_requests"][0]["id"] == "PR-5"


def test_a_repository_without_the_layer_gets_unchanged_replies(repo):
    root, s = repo
    git(root, "remote", "set-url", "origin", "https://gitlab.com/acme/widgets.git")
    build_graph(root)
    api = process_api.ProcessAPI(str(root), telemetry=False)
    h = api.call("history", files=["app.py"])
    assert "coverage" not in h and all("pr" not in c for c in h["commits"])
    assert "coverage" not in api.call("review_pack", rev=s["squash"])


def test_pull_request_tool_and_pack(online_api):
    api, s, root = online_api
    pr = api.call("pull_request", pr="5")
    assert pr["pr"] == "PR-5" and pr["n_commits"] == 3 and pr["closes"][0]["id"] == "GH-7"
    assert api.call("pull_request", pr="#5")["pr"] == "PR-5" and "error" in api.call("pull_request", pr="404")

    text = packs.Packer(api).pr("5")
    assert "# Graph pack: pull request PR-5 (Add gamma)" in text
    assert "## Commits it brought in (3)" in text and s["b1"][:10] in text
    assert "`GH-7` Gamma is missing (confidence 1.0)" in text
    assert "`app.py::gamma`" in text, "the function the pull request added"
    assert "tests/test_app.py" in text and "Run: `" in text, "the test that calls it"
    assert "**Complete.**" in text


def test_pr_pack_marks_what_the_offline_layer_could_not_verify(offline_api):
    api, s, _ = offline_api
    text = packs.Packer(api).pr("PR-6")
    assert "**unverified**" in text and "**Incomplete** (GitHub layer: offline)" in text and "`GH-8`" in text
    assert "no pull request 99" in packs.Packer(api).pr("99")


def test_ticket_pack_lists_pull_requests_commits_functions_and_tests(online_api):
    api, s, _ = online_api
    text = packs.Packer(api).ticket("GH-7")
    assert "## Pull requests that close it (1)" in text and "`PR-5` (merged, merge) Add gamma" in text
    assert "`app.py::gamma`" in text and "tests/test_app.py" in text
    offline = packs.Packer(process_api.ProcessAPI(str(online_api[2]), telemetry=False)).ticket("GH-7")
    assert "Pull-request links:" in offline


def test_pack_cli_accepts_pr_and_ticket(online_api, capsys, monkeypatch):
    api, s, root = online_api
    monkeypatch.setattr(sys, "argv", ["packs", "--project", str(root), "pr", "6"])
    assert packs.main() == 0
    assert "pull request PR-6" in capsys.readouterr().out


def test_cli_build_parses_the_github_flags_and_devkb_json_follows_them(repo, monkeypatch):
    """`devkb build --github` and `--no-github` through the real argument parsers of both stages."""
    root, s = repo
    fake = FakeGitHub(s)
    monkeypatch.setattr(github, "resolve_token", lambda host: "test-token")
    monkeypatch.setattr(github, "http_transport", lambda host, token, timeout=60.0: fake)

    def run(*flags):
        for module in (build_symbols, build_mod):
            monkeypatch.setattr(sys, "argv", [module.__name__, "--project", str(root), *flags])
            assert module.main() == 0
        return json.loads((root / ".devkb" / "manifest.json").read_text())["github"]

    assert run("--github")["mode"] == "online" and fake.calls, "--github fetched through the transport"
    calls = len(fake.calls)
    (root / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    assert run("--no-github")["mode"] == "offline" and len(fake.calls) == calls, "--no-github overrides devkb.json"


def test_graph_verbs_and_types_are_registered():
    from devkb.model import NODE_TYPES, VERBS
    assert "PullRequest" in NODE_TYPES and "MERGES" in VERBS and "CLOSES" in VERBS
    assert pull_requests.closing_numbers("Fixes #1, #2 and closes: #3; resolved #4. See #5 or fix owner/repo#6") == {1, 2, 3, 4}


def test_member_graph_prefixes_pull_request_and_issue_keys():
    from devkb.extractors import members
    assert members._prefixed("LIB", "PullRequest", "PR-5") == "LIB:PR-5" and members._prefixed("LIB", "Ticket", "GH-7") == "LIB:GH-7"


# ── fixes found by the blind review (ADR-DEVKB-007, before merging) ─────────────────────────
class Paged(FakeGitHub):
    """Serves the pull-request listing one record per page, and fails with a rate limit on the request numbered
    `fail_at` (counting every request), as a large first build does when it runs out of its hourly budget."""

    def __init__(self, shas, fail_at=None):
        super().__init__(shas)
        self.fail_at, self.n = fail_at, 0

    def __call__(self, query, variables):
        self.n += 1
        self.calls.append((query, dict(variables)))
        if self.fail_at and self.n == self.fail_at:
            raise github.GitHubError("rate-limited", "budget spent")
        if "pullRequests(" in query:
            ordered = sorted(self.prs, key=lambda p: p["updatedAt"], reverse=True)
            i = int(variables.get("after") or 0)
            return {"data": {"repository": {"pullRequests": {
                "pageInfo": {"hasNextPage": i + 1 < len(ordered), "endCursor": str(i + 1)}, "nodes": ordered[i:i + 1]}}}}
        return super().__call__(query, variables)


def test_a_first_build_cut_short_by_the_rate_limit_resumes_where_it_stopped(repo):
    root, s = repo
    first = Paged(s, fail_at=3)                      # pages 1-2 read, the third request is refused
    build_graph(root, github=True, github_transport=first)
    state = json.loads((root / ".devkb" / "github" / "pull_requests.json").read_text())
    assert state["complete"] is False and state["cursor"] == "2" and len(state["items"]) == 2, "progress is kept"
    manifest = json.loads((root / ".devkb" / "manifest.json").read_text())["github"]
    assert "pull_requests" in manifest["listing_incomplete"]

    second = Paged(s)
    graph, _ = build_graph(root, github=True, github_transport=second)
    pr_pages = [v for q, v in second.calls if "pullRequests(" in q]
    assert pr_pages[0]["after"] == "2", "the second build resumes from the saved cursor, not from page 1"
    assert {n.natural_key for n in graph.nodes("PullRequest") if n.source == "github-pull-requests"} == {"PR-5", "PR-6", "PR-9", "PR-11"}
    state = json.loads((root / ".devkb" / "github" / "pull_requests.json").read_text())
    assert state["complete"] is True and state["cursor"] is None


def test_a_failed_commit_continuation_costs_one_list_not_the_page(repo):
    root, s = repo

    class Long(FakeGitHub):
        def __call__(self, query, variables):
            if "pullRequest(number" in query:
                self.calls.append((query, dict(variables)))
                raise github.GitHubError("rate-limited", "commits ran out")
            return super().__call__(query, variables)

    fake = Long(s)
    fake.prs[0]["commits"]["pageInfo"] = {"hasNextPage": True, "endCursor": "c1"}
    fake.prs[0]["commits"]["totalCount"] = 150
    graph, devkb_dir = build_graph(root, github=True, github_transport=fake)
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["status"] == "ok" and report["commit_lists_not_fetched"] == [5]
    assert node(graph, "PullRequest", "PR-6").source == "github-pull-requests", "the rest of the page was kept"
    assert edges(graph, "MERGES")[("PR-5", s["b1"])].confidence == 1.0


def test_closing_references_to_another_repository_are_not_this_repositorys_issues(repo):
    root, s = repo
    fake = FakeGitHub(s)
    fake.prs[0]["closingIssuesReferences"] = {"nodes": [{"number": 7, "repository": {"nameWithOwner": "acme/widgets"}},
                                                        {"number": 99, "repository": {"nameWithOwner": "other/lib"}}]}
    graph, _ = build_graph(root, github=True, github_transport=fake)
    assert {dst for (src, dst) in edges(graph, "CLOSES") if src == "PR-5"} == {"GH-7"}
    assert node(graph, "Ticket", "GH-99") is None


def test_a_closed_issue_missing_from_the_listing_is_marked_not_fetched(repo):
    root, s = repo
    fake = FakeGitHub(s)
    fake.issues = [i for i in fake.issues if i["number"] != 7]
    graph, _ = build_graph(root, github=True, github_transport=fake)
    gh7 = node(graph, "Ticket", "GH-7")
    assert gh7.source == "github-closing-reference" and gh7.props["fetched"] is False


def test_a_number_github_returns_as_an_issue_is_not_an_offline_pull_request(repo):
    root, s = repo
    commit(root, {"notes.txt": "n3\n"}, "Document the limits (#12)")   # a squash-shaped subject naming issue 12
    fake = FakeGitHub(s)
    fake.issues.append({**fake.issues[1], "number": 12, "title": "Limits are undocumented", "url": "https://github.com/acme/widgets/issues/12"})
    graph, _ = build_graph(root, github=True, github_transport=fake)
    assert node(graph, "PullRequest", "PR-12") is None and node(graph, "Ticket", "GH-12") is not None
    offline, _ = build_graph(root)
    assert node(offline, "PullRequest", "PR-12") is not None, "offline, the subject is all there is"


def test_an_issue_with_sub_issues_answers_to_epics_and_keeps_its_type(repo):
    root, s = repo
    fake = FakeGitHub(s)
    fake.issues[2]["issueType"] = {"name": "Bug"}                 # #10 has a sub-issue
    graph, _ = build_graph(root, github=True, github_transport=fake)
    gh10 = node(graph, "Ticket", "GH-10")
    assert gh10.props["ticket_type"] == "BUG" and gh10.props["has_sub_issues"] is True
    from devkb import query
    with_epics = [n for n in graph.nodes("Ticket") if n.props.get("ticket_type") == "EPIC" or n.props.get("has_sub_issues")]
    assert [n.natural_key for n in with_epics] == ["GH-10"]
    assert "has_sub_issues" in Path(query.__file__).read_text()


def test_an_enterprise_host_accepts_github_token_only_where_ci_names_that_host(monkeypatch):
    monkeypatch.setattr(github.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no gh")))
    for name in ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_HOST", "GITHUB_SERVER_URL", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ci-token")
    assert github.resolve_token("git.corp.example") is None, "a github.com token is not sent to another host"
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://git.corp.example")
    assert github.resolve_token("git.corp.example") == "ci-token"


def test_a_merge_too_large_to_expand_is_reported(repo, monkeypatch):
    root, s = repo
    monkeypatch.setattr(pull_requests, "MAX_BROUGHT_IN", 1)
    _graph, devkb_dir = build_graph(root)
    report = json.loads((devkb_dir / "manifest.json").read_text())["github"]
    assert report["merges_not_expanded"] == [5]
