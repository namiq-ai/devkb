"""ADR-DEVKB-007: pull requests and hosted issues join the graph.

Every repository here is a throwaway git repository built in tmp_path; the GitHub API is a fake transport. No test
opens a connection: `make_transport` and `urlopen` are replaced by functions that fail the test if they are reached.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build, cli, github_api, index, packs, process_api  # noqa: E402
from devkb.extractors import members, pull_requests  # noqa: E402
from devkb.github_api import GitHubError  # noqa: E402
from devkb.model import NODE_TYPES, VERBS  # noqa: E402

BODY_SECRET = "secret-description-text-9f3a"
LOGIN = "octo-login-xyz"
EMAIL = "reviewer-person@example.org"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _commit(root: Path, path: str, text: str, message: str) -> str:
    (root / path).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any attempt to reach GitHub fails the test, unless a test installs its own fake transport."""
    def boom(*a, **k):
        raise AssertionError("the network was used")
    monkeypatch.setattr(github_api, "make_transport", boom)
    monkeypatch.setattr(github_api.urllib.request, "urlopen", boom)
    monkeypatch.setattr(github_api, "find_token", boom)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main: init; a feature branch merged with a merge commit (#5, body `Fixes #7`); a squash commit (#6, `Closes #8, #9`);
    a subject ending (#10) that is really an issue; a bare mention of #8; two plain commits a rebase merge (#11) left."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "dev@example.com")
    _git(root, "config", "user.name", "Dev Person")
    _git(root, "remote", "add", "origin", "https://github.com/acme/widgets.git")
    (root / "pkg").mkdir()
    (root / "tests").mkdir()
    (root / "pkg" / "a.py").write_text("def alpha():\n    return 1\n\ndef beta():\n    return 2\n")
    (root / "tests" / "test_a.py").write_text("from pkg import a\n\ndef test_alpha():\n    a.alpha()\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    sha = {"init": _git(root, "rev-parse", "HEAD")}
    _git(root, "checkout", "-q", "-b", "feature-1")
    sha["c1"] = _commit(root, "pkg/a.py", "def alpha():\n    return 10\n\ndef beta():\n    return 2\n", "Add feature\n\nFixes #7")
    sha["c2"] = _commit(root, "pkg/b.py", "def gamma():\n    return 3\n", "Polish feature")
    _git(root, "checkout", "-q", "main")
    sha["m1"] = _commit(root, "README.md", "readme\n", "main work")
    _git(root, "merge", "--no-ff", "-q", "feature-1", "-m", "Merge pull request #5 from octocat/feature-1", "-m", "Add widget feature")
    sha["merge5"] = _git(root, "rev-parse", "HEAD")
    sha["squash6"] = _commit(root, "pkg/a.py", "def alpha():\n    return 11\n\ndef beta():\n    return 2\n",
                             "Tweak alpha (#6)\n\nCloses #8, #9")
    sha["issue10"] = _commit(root, "NOTES.md", "notes\n", "Mention the docs (#10)")
    sha["mention"] = _commit(root, "NOTES.md", "notes2\n", "Refs #8 in passing")
    sha["r1"] = _commit(root, "pkg/c.py", "def delta():\n    return 4\n", "rebase one")
    sha["r2"] = _commit(root, "pkg/c.py", "def delta():\n    return 5\n", "rebase two")
    monkeypatch.setenv("DEVKB_DIR", str(tmp_path / "kb"))
    monkeypatch.delenv("DEVKB_REPO", raising=False)
    monkeypatch.delenv("DEVKB_EXTERNAL", raising=False)
    return root, sha, tmp_path / "kb"


def _graph(kb: Path):
    nodes = {}
    for line in (kb / "nodes.jsonl").read_text().splitlines():
        n = json.loads(line)
        nodes[n["uid"]] = n
    by_key = {(n["type"], n["natural_key"]): n for n in nodes.values()}
    edges = []
    for line in (kb / "edges.jsonl").read_text().splitlines():
        e = json.loads(line)
        a, b = nodes.get(e["from_uid"]), nodes.get(e["to_uid"])
        edges.append((e["verb"], a["natural_key"], b["natural_key"], e["properties"]))
    return by_key, edges


def _edges(edges, verb, src=None):
    return [(s, d, p) for v, s, d, p in edges if v == verb and (src is None or s == src)]


# ── the fake API ──────────────────────────────────────────────────────────────
def _gql_pr(number, title, state, commits, closes=(), merge=None, labels=(), updated="2026-01-01T00:00:00Z", **extra):
    return {"number": number, "title": title, "state": state, "mergedAt": "2026-01-02T00:00:00Z" if state == "MERGED" else None,
            "updatedAt": updated, "baseRefName": "main", "headRefName": f"branch-{number}", "url": f"https://github.com/acme/widgets/pull/{number}",
            "labels": {"nodes": [{"name": n} for n in labels]}, "mergeCommit": {"oid": merge} if merge else None,
            "closingIssuesReferences": {"nodes": [{"number": n} for n in closes]},
            "commits": {"totalCount": len(commits), "pageInfo": {"hasNextPage": False, "endCursor": "x"},
                        "nodes": [{"commit": {"oid": c}} for c in commits]},
            "body": BODY_SECRET, "reviews": {"nodes": [{"body": BODY_SECRET}]}, **extra}


def _gql_issue(number, title, state="OPEN", labels=(), itype=None, parent=None, subs=0, updated="2026-01-01T00:00:00Z", **extra):
    return {"number": number, "title": title, "state": state, "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "url": f"https://github.com/acme/widgets/issues/{number}", "createdAt": "2025-12-01T00:00:00Z",
            "closedAt": "2026-01-01T00:00:00Z" if state == "CLOSED" else None, "updatedAt": updated,
            "milestone": {"title": "v1"} if number == 8 else None, "labels": {"nodes": [{"name": n} for n in labels]},
            "issueType": {"name": itype} if itype else None,
            "parent": {"number": parent, "repository": {"nameWithOwner": "acme/widgets"}} if parent else None,
            "subIssues": {"totalCount": subs}, "body": BODY_SECRET, "comments": {"nodes": [{"body": BODY_SECRET}]}, **extra}


class FakeGitHub:
    def __init__(self, prs, issues, page=100, fail_after=None):
        self.prs, self.issues, self.page, self.fail_after = prs, issues, page, fail_after
        self.queries: list[str] = []
        self.requests = 0

    def __call__(self, query, variables):
        self.requests += 1
        self.queries.append(query)
        if self.fail_after is not None and self.requests > self.fail_after:
            raise GitHubError("rate limited from github.com")
        kind = "pullRequests" if "pullRequests(" in query else "issues"
        items = sorted(self.prs if kind == "pullRequests" else self.issues, key=lambda n: n["updatedAt"], reverse=True)
        start = int(variables.get("after") or 0)
        chunk = items[start:start + self.page]
        end = start + len(chunk)
        return {"data": {"repository": {kind: {"totalCount": len(items), "pageInfo": {"hasNextPage": end < len(items), "endCursor": str(end)},
                                              "nodes": chunk}}}}


def _api(sha, **extra):
    prs = [
        _gql_pr(5, "Add widget feature", "MERGED", [sha["c1"], sha["c2"]], closes=[7], merge=sha["merge5"], labels=["feature"], **extra),
        _gql_pr(6, "Tweak alpha", "MERGED", ["0" * 40], closes=[8], merge=sha["squash6"]),
        _gql_pr(11, "Delta by rebase", "MERGED", [sha["r1"], sha["r2"]], merge=sha["r2"]),
        _gql_pr(12, "Still open", "OPEN", [sha["c1"]], closes=[7]),
    ]
    issues = [
        _gql_issue(7, "Alpha is wrong", "CLOSED", labels=["bug"]),
        _gql_issue(8, "Epic: rework alpha", "CLOSED", subs=2),
        _gql_issue(9, "Child of the epic", "OPEN", labels=["enhancement"], parent=8),
        _gql_issue(10, "Docs request", "OPEN", itype="Task"),
        _gql_issue(13, "A planned story", "OPEN", labels=["epic"]),
    ]
    return prs, issues


@pytest.fixture
def online(monkeypatch):
    def install(fake):
        monkeypatch.setattr(github_api, "make_transport", lambda remote, token: fake)
        monkeypatch.setattr(github_api, "find_token", lambda host: "t0ken")
        return fake
    return install


# ── ontology ───────────────────────────────────────────────────────────────────
def test_the_ontology_names_the_new_type_and_verbs():
    assert "PullRequest" in NODE_TYPES and "MERGES" in VERBS and "CLOSES" in VERBS
    text = (_REPO_ROOT / "devkb" / "ontology.md").read_text()
    for term in ("PullRequest", "MERGES", "CLOSES", "git-merge-subject", "git-squash-subject", "github-sub-issues",
                 "git-hash-mention", "GH-<number>", "--github", ".devkb/github/", "authors"):
        assert term in text, term


# ── offline layer ──────────────────────────────────────────────────────────────
def test_offline_layer_finds_merge_and_squash_pull_requests(repo):
    root, sha, kb = repo
    build.build(str(root))
    nodes, edges = _graph(kb)
    pr5, pr6 = nodes[("PullRequest", "PR-5")], nodes[("PullRequest", "PR-6")]
    assert pr5["source"] == "git-merge-subject" and pr6["source"] == "git-squash-subject"
    p5 = pr5["properties"]
    assert (p5["number"], p5["title"], p5["state"], p5["head"], p5["merge_style"]) == (5, "Add widget feature", "merged", "feature-1", "merge")
    assert p5["url"] == "https://github.com/acme/widgets/pull/5" and p5["merged_at"]
    assert pr6["properties"]["title"] == "Tweak alpha" and pr6["properties"]["merge_style"] == "squash"
    merges5 = {d: p for s, d, p in _edges(edges, "MERGES", "PR-5")}
    assert set(merges5) == {sha["merge5"], sha["c1"], sha["c2"]}, "the merge commit and the commits it brought in, not main's own"
    assert all(p["confidence"] == 0.9 and p["source"] == "git-merge-subject" for p in merges5.values())
    assert {d for s, d, p in _edges(edges, "MERGES", "PR-6")} == {sha["squash6"]}
    assert _edges(edges, "MERGES", "PR-6")[0][2]["source"] == "git-squash-subject"
    assert ("PullRequest", "PR-11") not in nodes, "a rebase merge leaves no trace in git"


def test_offline_closing_keywords_are_unverified_and_a_bare_mention_gives_no_edge(repo):
    root, sha, kb = repo
    build.build(str(root))
    nodes, edges = _graph(kb)
    closes = {(s, d): p for s, d, p in _edges(edges, "CLOSES")}
    assert set(closes) == {("PR-5", "GH-7"), ("PR-6", "GH-8"), ("PR-6", "GH-9")}
    for p in closes.values():
        assert p["confidence"] == 0.7 and p["unverified"] is True and p["source"] == "git-closing-keyword"
    assert nodes[("Ticket", "GH-7")]["properties"]["unverified"] is True
    assert not [e for e in edges if e[0] == "REFERENCES" and e[2].startswith("GH-")], "offline, `#N` alone is never an issue link"
    assert ("PullRequest", "PR-10") in nodes, "offline cannot tell that (#10) is an issue; the online layer corrects it"


def test_manifest_records_the_layer(repo):
    root, _, kb = repo
    build.build(str(root))
    gh = json.loads((kb / "manifest.json").read_text())["github"]
    assert gh["status"] == "off" and gh["requested"] is False and gh["offline_pull_requests"] == 3 and gh["unverified_closes"] == 3


def test_no_remote_no_new_nodes(repo):
    root, _, kb = repo
    _git(root, "remote", "remove", "origin")
    build.build(str(root))
    nodes, _ = _graph(kb)
    assert not [k for k in nodes if k[0] == "PullRequest"] and not [k for k in nodes if k[1].startswith("GH-")]
    assert "github" not in json.loads((kb / "manifest.json").read_text())


# ── no network by default (validation 4) ───────────────────────────────────────
def test_a_build_without_the_flag_makes_no_request(repo, monkeypatch):
    root, _, kb = repo
    asked = []
    monkeypatch.setattr(github_api, "fetch", lambda *a, **k: asked.append(1))
    graph, _ = build.build(str(root))          # no_network fixture fails the test if a transport, token or urlopen is reached
    assert graph.node_count() and not asked and not (kb / "github").exists()


def test_flag_and_devkb_json_turn_the_online_layer_on(repo):
    root, _, _ = repo
    assert github_api.settings(root) == {"enabled": False, "authors": False}
    assert github_api.settings(root, flag=True)["enabled"] is True
    (root / "devkb.json").write_text(json.dumps({"github": {"enabled": True, "authors": True}}))
    assert github_api.settings(root) == {"enabled": True, "authors": True}


def test_cli_passes_github_to_the_process_build_only(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_run", lambda module, argv: calls.append((module, argv)) or 0)
    cli.main(["build", "--project", ".", "--github"])
    assert calls == [("devkb.build_symbols", ["--project", "."])] or calls[0] == ("devkb.build_symbols", ["--project", "."])


def test_build_main_accepts_the_flag(repo, online, monkeypatch):
    root, sha, kb = repo
    online(FakeGitHub(*_api(sha)))
    monkeypatch.setattr(sys, "argv", ["build", "--project", str(root), "--github"])
    assert build.main() == 0
    assert json.loads((kb / "manifest.json").read_text())["github"]["status"] == "ok"


# ── online layer ───────────────────────────────────────────────────────────────
def test_online_layer_confirms_corrects_and_extends(repo, online):
    root, sha, kb = repo
    fake = online(FakeGitHub(*_api(sha), page=2))
    build.build(str(root), github=True)
    nodes, edges = _graph(kb)

    # pull requests: API properties, confidence 1.0 commit lists, rebase merges visible
    p5 = nodes[("PullRequest", "PR-5")]["properties"]
    assert p5["base"] == "main" and p5["head"] == "branch-5" and p5["labels"] == ["feature"] and p5["merge_style"] == "merge"
    assert {d for s, d, p in _edges(edges, "MERGES", "PR-5")} == {sha["merge5"], sha["c1"], sha["c2"]}
    assert all(p["confidence"] == 1.0 and p["source"] == "github-pr-commits" for s, d, p in _edges(edges, "MERGES", "PR-5"))
    assert {d for s, d, p in _edges(edges, "MERGES", "PR-11")} == {sha["r1"], sha["r2"]}
    assert not _edges(edges, "MERGES", "PR-12"), "an open pull request has merged nothing"
    assert nodes[("PullRequest", "PR-12")]["properties"]["state"] == "open"
    assert ("PullRequest", "PR-10") not in nodes, "(#10) is an issue: GitHub numbers both from one sequence"

    # closes: GitHub's record replaces the keyword guesses
    closes = {(s, d): p for s, d, p in _edges(edges, "CLOSES")}
    assert set(closes) == {("PR-5", "GH-7"), ("PR-6", "GH-8"), ("PR-12", "GH-7")}, "the API does not confirm `Closes #9`; it is removed"
    assert all(p["confidence"] == 1.0 and "unverified" not in p for p in closes.values())
    assert nodes[("Ticket", "GH-7")]["properties"].get("unverified") is None

    # issues as tickets
    t7, t8, t9, t10, t13 = (nodes[("Ticket", f"GH-{n}")] for n in (7, 8, 9, 10, 13))
    assert t7["source"] == "github-issues" and t7["properties"]["ticket_type"] == "BUG"
    assert t7["properties"]["state"] == "closed" and t7["properties"]["state_reason"] == "completed"
    assert t7["properties"]["closed_at"] and t7["properties"]["created_at"] and t7["properties"]["url"].endswith("/issues/7")
    assert t8["properties"]["ticket_type"] == "EPIC" and t8["properties"]["milestone"] == "v1", "sub-issues make an epic"
    assert t9["properties"]["ticket_type"] == "FEATURE" and t10["properties"]["ticket_type"] == "TASK"
    assert t13["properties"]["ticket_type"] == "EPIC"
    child = _edges(edges, "CHILD_OF", "GH-9")
    assert [(d, p["source"]) for s, d, p in child] == [("GH-8", "github-sub-issues")]

    # a bare mention resolves now
    refs = [(s, d, p) for s, d, p in _edges(edges, "REFERENCES") if d.startswith("GH-")]
    assert {(s, d) for s, d, _ in refs} == {(sha["mention"], "GH-8"), (sha["c1"], "GH-7"), (sha["squash6"], "GH-8"), (sha["squash6"], "GH-9"),
                                                  (sha["issue10"], "GH-10")}, "a message that names an issue GitHub knows"
    assert all(p["source"] == "git-hash-mention" and p["confidence"] == 0.8 for _, _, p in refs)
    gh = json.loads((kb / "manifest.json").read_text())["github"]
    assert gh["status"] == "ok" and gh["pull_requests"] == 4 and gh["issues"] == 5 and fake.requests >= 4, "paged two at a time"


def test_cache_means_a_rebuild_fetches_only_what_changed(repo, online):
    root, sha, kb = repo
    prs, issues = _api(sha)
    fake = online(FakeGitHub(prs, issues, page=2))
    build.build(str(root), github=True)
    assert (kb / "github" / "pull_requests.json").is_file() and (kb / "github" / "issues.json").is_file()
    assert (kb / "github" / ".gitignore").read_text().strip() == "*"
    first = fake.requests
    build.build(str(root), github=True)
    second = fake.requests - first
    assert second == 2, "one page per kind, then stop: nothing on it changed"
    # an item changed upstream: it is refetched and the graph follows
    issues[4]["title"], issues[4]["updatedAt"] = "A planned story, renamed", "2026-02-01T00:00:00Z"
    build.build(str(root), github=True)
    nodes, _ = _graph(kb)
    assert nodes[("Ticket", "GH-13")]["properties"]["title"] == "A planned story, renamed"


def test_pull_request_with_more_than_a_page_of_commits(repo, online):
    root, sha, kb = repo
    prs, issues = _api(sha)
    prs[0]["commits"]["pageInfo"] = {"hasNextPage": True, "endCursor": "c1"}
    prs[0]["commits"]["nodes"] = [{"commit": {"oid": sha["c1"]}}]
    prs[0]["commits"]["totalCount"] = 2

    class Fake(FakeGitHub):
        def __call__(self, query, variables):
            if "pullRequest(number" in query:
                assert variables["number"] == 5 and variables["after"] == "c1"
                return {"data": {"repository": {"pullRequest": {"commits": {"pageInfo": {"hasNextPage": False, "endCursor": "z"},
                                                                          "nodes": [{"commit": {"oid": sha["c2"]}}]}}}}}
            return super().__call__(query, variables)
    online(Fake(prs, issues))
    build.build(str(root), github=True)
    _, edges = _graph(kb)
    assert {d for s, d, p in _edges(edges, "MERGES", "PR-5")} >= {sha["c1"], sha["c2"]}


# ── when GitHub cannot be reached ──────────────────────────────────────────────
def test_unreachable_api_degrades_to_the_offline_layer_and_says_so(repo, online, capsys):
    root, sha, kb = repo
    online(FakeGitHub(*_api(sha), fail_after=0))
    build.build(str(root), github=True)             # completes
    assert "rate limited" in capsys.readouterr().err
    nodes, edges = _graph(kb)
    assert ("PullRequest", "PR-5") in nodes and _edges(edges, "MERGES", "PR-5") and ("PullRequest", "PR-11") not in nodes
    assert {p["confidence"] for s, d, p in _edges(edges, "CLOSES")} == {0.7}, "unverified offline links stay, marked"
    gh = json.loads((kb / "manifest.json").read_text())["github"]
    assert gh["status"] == "unreachable" and gh["requested"] is True and "rate limited" in gh["errors"][0]
    api = process_api.ProcessAPI(str(root), use_cache=False, telemetry=False)
    note = api.call("lineage", ticket="GH-7")["coverage"]
    assert "not reached" in note and "rate limited" in note and "unverified" in note


def test_no_credentials_is_a_reported_failure_not_a_crash(repo, monkeypatch, capsys):
    root, _, kb = repo
    monkeypatch.setattr(github_api, "find_token", lambda host: None)
    build.build(str(root), github=True)
    assert "no credentials" in capsys.readouterr().err
    assert json.loads((kb / "manifest.json").read_text())["github"]["status"] == "unreachable"


def test_partial_fetch_keeps_what_it_got(repo, online):
    root, sha, kb = repo
    prs, issues = _api(sha)
    online(FakeGitHub(prs, issues, page=2, fail_after=1))      # the second page of pull requests is refused
    build.build(str(root), github=True)
    gh = json.loads((kb / "manifest.json").read_text())["github"]
    assert gh["status"] == "partial" and gh["errors"] and gh["pull_requests"] == 2 and gh["pull_requests_total"] == 4
    nodes, edges = _graph(kb)
    api = process_api.ProcessAPI(str(root), use_cache=False, telemetry=False)
    assert "incomplete" in api.call("history", files=["pkg/a.py"])["coverage"]
    # the PRs not fetched stay offline-derived, still unverified; nothing is dropped on a partial listing
    assert ("PullRequest", "PR-10") in nodes


# ── privacy (validation 5) ─────────────────────────────────────────────────────
def _everything_under(kb: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in kb.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".md", ""))


def test_no_description_review_or_author_is_written_by_default(repo, online):
    root, sha, kb = repo
    prs, issues = _api(sha, author={"login": LOGIN, "email": EMAIL}, reviews={"nodes": [{"body": BODY_SECRET, "author": {"login": LOGIN}}]})
    issues[0]["author"] = {"login": LOGIN}
    fake = online(FakeGitHub(prs, issues))
    build.build(str(root), github=True)
    blob = _everything_under(kb)
    assert "GH-7" in blob and "PR-5" in blob
    for secret in (BODY_SECRET, LOGIN, EMAIL):
        assert secret not in blob, secret
    assert not any("author" in q or "body" in q.lower().replace("pageinfo", "") or "comments" in q or "reviews" in q for q in fake.queries), \
        "the query does not even ask for them"


def test_author_login_is_stored_only_when_the_repository_opts_in(repo, online):
    root, sha, kb = repo
    prs, issues = _api(sha, author={"login": LOGIN})
    issues[0]["author"] = {"login": LOGIN}
    fake = online(FakeGitHub(prs, issues))
    build.build(str(root), github=True)                          # no opt-in: nothing, and the cache is private-setting aware
    assert LOGIN not in _everything_under(kb)
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    build.build(str(root), github=True)
    nodes, _ = _graph(kb)
    assert nodes[("PullRequest", "PR-5")]["properties"]["author"] == LOGIN
    assert nodes[("Ticket", "GH-7")]["properties"]["author"] == LOGIN
    assert any("author { login }" in q for q in fake.queries)
    assert BODY_SECRET not in _everything_under(kb) and EMAIL not in _everything_under(kb)
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": False}}))
    build.build(str(root), github=True)                          # opting out again removes it, cache included
    assert LOGIN not in _everything_under(kb)


# ── tools ──────────────────────────────────────────────────────────────────────
def _api_of(root):
    return process_api.ProcessAPI(str(root), use_cache=False, telemetry=False)


def test_tools_follow_merges_and_closes(repo, online):
    root, sha, kb = repo
    online(FakeGitHub(*_api(sha)))
    build.build(str(root), github=True)
    api = _api_of(root)

    trace = api.call("trace", ticket="GH-7")
    assert [r["pr"] for r in trace["closed_by"]] == ["PR-5", "PR-12"] and trace["type"] == "BUG"
    assert api.call("trace", ticket="GH-9")["epic"] == [{"id": "GH-8", "status": "OPEN"}] or api.call("trace", ticket="GH-9")["epic"][0]["id"] == "GH-8"

    lin = api.call("lineage", ticket="GH-7")
    assert [r["pr"] for r in lin["pull_requests"]] == ["PR-5", "PR-12"]
    assert lin["commits"] >= 3 and lin["first"] and "coverage" not in lin, "complete online data states no gap"
    assert api.call("lineage", ticket="GH-8")["children"] == ["GH-9"]

    ctx = api.call("sdlc_context", ticket="GH-7")
    assert ctx["pull_requests"][0]["pr"] == "PR-5" and ctx["commits"] >= 3

    hist = api.call("history", files=["pkg/c.py"])
    assert any(c.get("pr") == [11] for c in hist["commits"])
    hist5 = api.call("history", files=["pkg/b.py"])
    row = next(c for c in hist5["commits"] if c["h"] == sha["c2"][:8])
    assert row["pr"] == [5] and "GH-7" in row["t"]

    rp = api.call("review_pack", rev=f"{sha['init']}..{sha['merge5']}")
    assert [r["pr"] for r in rp["pull_requests"]] == ["PR-5"] and "GH-7" in rp["tickets"]


def test_offline_answers_state_that_links_are_unverified(repo):
    root, sha, kb = repo
    build.build(str(root))
    api = _api_of(root)
    lin = api.call("lineage", ticket="GH-7")
    assert lin["pull_requests"][0]["pr"] == "PR-5"
    assert "git alone" in lin["coverage"] and "1 issue link(s) marked unverified" in lin["coverage"] and "--github" in lin["coverage"]
    assert "git alone" in api.call("history", files=["pkg/a.py"])["coverage"]
    assert api.call("graph_status")["pull_requests"] == 3


def test_tickets_from_files_are_not_given_a_github_note(repo):
    root, _, kb = repo
    (root / "issues").mkdir()
    (root / "issues" / "APP-1_BUG_P1_S1_2026-01-01_2026-01-02_DONE_core_dev.md").write_text("# APP-1: file ticket\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "APP-1 file ticket")
    (root / "devkb.json").write_text(json.dumps({"ticket_prefix": "APP"}))
    build.build(str(root))
    assert "coverage" not in _api_of(root).call("lineage", ticket="APP-1")


def test_packs_pr_and_ticket(repo, online, capsys):
    root, sha, kb = repo
    online(FakeGitHub(*_api(sha)))
    build.build(str(root), github=True)
    pk = packs.Packer(_api_of(root))
    text = pk.pr("5")
    assert text.startswith("# Graph pack: pull request PR-5 (Add widget feature)")
    for part in ("State: merged", "## Commits it brought in (3)", "Add feature", "## Issues it closes (1)", "`GH-7` Alpha is wrong",
                 "## Module-level functions it changed", "## Test files to run", "## Coverage"):
        assert part in text, part
    assert "unverified" not in text
    assert pk.pr("PR-5") == text and pk.pr("#5") == text
    assert "no pull request PR-99" in pk.pr("99")
    tk = pk.ticket("GH-7")
    assert "## Pull requests that close it (2)" in tk and "`PR-5` merged" in tk and "`PR-12` open" in tk
    assert "or merged by those pull requests" in tk


def test_pack_states_unverified_links_and_coverage_offline(repo):
    root, sha, kb = repo
    build.build(str(root))
    text = packs.Packer(_api_of(root)).pr("6")
    assert "`GH-8`" in text and "**unverified**" in text and "git alone" in text and "2 issue link(s) marked unverified" in text


def test_pack_functions_from_symbols_and_tests(repo):
    """With the symbol graph built, the pack names the functions a pull request changed and the tests that call them."""
    from devkb import build_symbols
    root, sha, kb = repo
    build_symbols.build(str(root))
    build.build(str(root))
    text = packs.Packer(_api_of(root)).pr("5")
    assert "`pkg/a.py::alpha`" in text and "`pkg/b.py::gamma`" in text
    assert "`tests/test_a.py`" in text


def test_devkb_pack_pr_on_the_command_line(repo, monkeypatch, capsys):
    root, sha, kb = repo
    build.build(str(root))
    monkeypatch.chdir(root)
    assert cli.main(["pack", "pr", "5"]) == 0
    assert "# Graph pack: pull request PR-5" in capsys.readouterr().out


def test_query_reaches_pull_requests(repo):
    root, sha, kb = repo
    build.build(str(root))
    from devkb import query
    idx = index.load(kb)
    assert query._find_node(idx, "PR-5")["type"] == "PullRequest"


# ── small units ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,expected", [
    ("https://github.com/acme/widgets.git", ("github.com", "acme", "widgets")),
    ("https://user:pw@github.com/acme/widgets", ("github.com", "acme", "widgets")),
    ("git@github.com:acme/widgets.git", ("github.com", "acme", "widgets")),
    ("ssh://git@ghe.example.com:2222/acme/widgets.git", ("ghe.example.com", "acme", "widgets")),
    ("/some/local/path", None), ("", None),
])
def test_parse_remote(url, expected):
    r = github_api.parse_remote(url)
    assert (None if r is None else (r.host, r.owner, r.repo)) == expected


def test_ticket_type_rules():
    t = github_api.ticket_type
    assert t("Bug", ["feature"]) == "BUG", "the issue type wins over labels"
    assert t(None, ["Epic"]) == "EPIC" and t(None, ["enhancement"]) == "FEATURE" and t(None, ["feature"]) == "FEATURE"
    assert t(None, ["bug"]) == "BUG" and t(None, ["question"]) == "ISSUE" and t(None, []) == "ISSUE"


def test_closing_keyword_parsing():
    f = pull_requests.closing_numbers
    assert f(["Fixes #1, #2 and #3\nCloses: #4\nresolved #5"], 99) == [1, 2, 3, 4, 5]
    assert f(["Fixes #9 and also mentions #8", "prefix fixed #7"], 9) == [7], "own number excluded; a plain mention is not a link"
    assert f(["Fixes owner/repo#12", "closest #3"], 1) == []


def test_member_pull_request_keys_are_prefixed():
    assert members._prefixed("LIB", "PullRequest", "PR-3") == "LIB:PR-3"
    assert members._prefixed("LIB", "Ticket", "GH-3") == "LIB:GH-3"
