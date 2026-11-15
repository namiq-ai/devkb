"""ADR-DEVKB-007: pull requests and hosted issues. Fixture git repositories; the GitHub API is mocked, no test uses the network."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build, build_symbols, github_api, process_api  # noqa: E402
from devkb.extractors import pull_requests  # noqa: E402
from devkb.model import NODE_TYPES, VERBS  # noqa: E402
from devkb.packs import Packer  # noqa: E402
from devkb.project_context import github_config, resolve  # noqa: E402

SECRET = "SECRET-DESCRIPTION-TEXT"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every test runs with sockets closed; the API is only ever the mock a test installs."""
    def refuse(*a, **k):
        raise AssertionError("the network was used")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(github_api, "http_request", refuse)
    monkeypatch.delenv("DEVKB_DIR", raising=False)
    monkeypatch.delenv("DEVKB_REPO", raising=False)
    monkeypatch.setattr(github_api, "find_token", lambda host: "test-token")


def git(root: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "Dev Person", "GIT_AUTHOR_EMAIL": "dev@example.com", "GIT_COMMITTER_NAME": "Dev Person",
           "GIT_COMMITTER_EMAIL": "dev@example.com", "PATH": __import__("os").environ["PATH"], "HOME": str(root)}
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env).stdout.strip()


APP = "def helper():\n    return 1\n"


def make_repo(tmp_path: Path, remote: str | None = "https://github.com/acme/widgets.git") -> tuple[Path, dict]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text(APP)
    (root / "tests").mkdir()
    (root / "tests/test_app.py").write_text("from app import helper\n\n\ndef test_helper():\n    assert helper() == 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    # PR 5: a merge commit with two commits on the branch; the first says "Fixes #7"
    git(root, "checkout", "-qb", "feature-x")
    (root / "app.py").write_text(APP + "\n\ndef feature():\n    return helper() + 1\n")
    git(root, "commit", "-qam", "add feature\n\nFixes #7")
    first = git(root, "rev-parse", "HEAD")
    (root / "tests/test_feature.py").write_text("from app import feature\n\n\ndef test_feature():\n    assert feature() == 2\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "test the feature")
    second = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "--no-ff", "-m", f"Merge pull request #5 from octocat/feature-x\n\nAdd the feature", "feature-x")
    merge = git(root, "rev-parse", "HEAD")
    # PR 6: a squash commit; its message closes #8, which the API will contradict
    (root / "app.py").write_text((root / "app.py").read_text() + "\n\ndef parse():\n    return helper()\n")
    git(root, "commit", "-qam", f"Fix the parser (#6)\n\nCloses #8\n{SECRET}")
    squash = git(root, "rev-parse", "HEAD")
    # a plain commit that mentions issue 7 without a closing keyword
    (root / "notes.txt").write_text("n\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "follow up on #7")
    mention = git(root, "rev-parse", "HEAD")
    if remote:
        git(root, "remote", "add", "origin", remote)
    return root, {"first": first, "second": second, "merge": merge, "squash": squash, "mention": mention}


def issue(n, title, updated, **extra):
    return {"number": n, "title": title, "state": "closed", "state_reason": "completed", "labels": [], "milestone": None,
            "html_url": f"https://github.com/acme/widgets/issues/{n}", "created_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-02-01T00:00:00Z", "updated_at": updated, "type": None, "body": SECRET,
            "user": {"login": "mallory"}, **extra}


class FakeGitHub:
    """Serves the fixture repository's GitHub side and counts requests per endpoint."""

    def __init__(self, shas: dict, closes: dict | None = None, fail: str | None = None) -> None:
        self.shas, self.fail, self.calls = shas, fail, {"issues": 0, "pulls": 0, "graphql": 0}
        self.closes = closes if closes is not None else {5: [7], 6: []}
        self.issues = [
            issue(9, "Sub task", "2026-03-03T00:00:00Z", labels=[{"name": "enhancement"}],
                  parent_issue_url="https://api.github.com/repos/acme/widgets/issues/8"),
            issue(8, "Big epic", "2026-03-02T00:00:00Z", labels=[{"name": "epic"}], sub_issues_summary={"total": 1, "completed": 0},
                  milestone={"title": "v1"}),
            issue(7, "Crash on start", "2026-03-01T00:00:00Z", type={"name": "Bug"}, labels=[{"name": "p1"}]),
            {**issue(5, "Add the feature", "2026-03-05T00:00:00Z"), "pull_request": {"url": "x"}},
        ]
        self.pulls = [
            {"number": 10, "title": "Open work", "state": "open", "merged_at": None, "updated_at": "2026-03-06T00:00:00Z",
             "base": {"ref": "main"}, "head": {"ref": "wip"}, "labels": [], "html_url": "u10", "user": {"login": "mallory"},
             "merge_commit_sha": None, "body": SECRET},
            {"number": 6, "title": "Fix the parser", "state": "closed", "merged_at": "2026-03-04T00:00:00Z",
             "updated_at": "2026-03-04T00:00:00Z", "base": {"ref": "main"}, "head": {"ref": "fix-parser"},
             "labels": [{"name": "bug"}], "html_url": "u6", "user": {"login": "mallory"}, "merge_commit_sha": shas["squash"]},
            {"number": 5, "title": "Add the feature", "state": "closed", "merged_at": "2026-03-03T00:00:00Z",
             "updated_at": "2026-03-05T00:00:00Z", "base": {"ref": "main"}, "head": {"ref": "feature-x"},
             "labels": [{"name": "enhancement"}], "html_url": "u5", "user": {"login": "mallory"}, "merge_commit_sha": shas["merge"]},
        ]

    @staticmethod
    def page(rows, url):
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(url).query)
        size, page = int(q["per_page"][0]), int(q["page"][0])
        return rows[(page - 1) * size: page * size]

    def __call__(self, url, token, body=None):
        assert token == "test-token" and "api.github.com" in url
        if self.fail:
            raise github_api.GitHubError(self.fail, "mocked failure")
        if "/graphql" in url:
            self.calls["graphql"] += 1
            nodes = [
                {"number": 6, "updatedAt": "2026-03-04T00:00:00Z", "mergeCommit": {"oid": self.shas["squash"]},
                 "commits": {"totalCount": 1, "nodes": [{"commit": {"oid": self.shas["squash"]}}]},
                 "closingIssuesReferences": {"nodes": [{"number": n, "repository": {"nameWithOwner": "acme/widgets"}} for n in self.closes[6]]}},
                {"number": 5, "updatedAt": "2026-03-05T00:00:00Z", "mergeCommit": {"oid": self.shas["merge"]},
                 "commits": {"totalCount": 2, "nodes": [{"commit": {"oid": self.shas["first"]}}, {"commit": {"oid": self.shas["second"]}}]},
                 "closingIssuesReferences": {"nodes": [{"number": n, "repository": {"nameWithOwner": "acme/widgets"}} for n in self.closes[5]]
                                             + [{"number": 99, "repository": {"nameWithOwner": "other/repo"}}]}},
            ]
            return {"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}
        if "/issues?" in url:
            self.calls["issues"] += 1
            return self.page(self.issues, url)
        if "/pulls?" in url:
            self.calls["pulls"] += 1
            return self.page(self.pulls, url)
        raise AssertionError(url)


def run_build(root: Path, monkeypatch, fake=None, **kw):
    if fake is not None:
        monkeypatch.setattr(github_api, "http_request", fake)
    build_symbols.build(str(root))
    graph, out = build.build(str(root), **kw)
    return graph, out


def nodes_of(graph, typ):
    return {n.natural_key: n for n in graph.nodes(typ)}


def edges_of(graph, verb):
    return {(e.src, e.dst): e for e in graph.edges(verb)}


# ── the vocabulary ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_ontology_gains_one_node_type_and_two_verbs_and_the_document_says_so():
    assert "PullRequest" in NODE_TYPES and {"MERGES", "CLOSES"} <= set(VERBS)
    text = (_REPO_ROOT / "devkb/ontology.md").read_text()
    for term in ("`PullRequest`", "`MERGES`", "`CLOSES`", "GH-", "git-merge-subject", "git-squash-subject", "github-sub-issues",
                 "git-hash-mention", "authors", ".devkb/github/"):
        assert term in text, term


# ── the offline layer ──────────────────────────────────────────────────────────────────────────────────────────
def test_offline_a_merge_commit_and_a_squash_commit_give_pull_requests_with_merges_at_0_9(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    graph, _ = run_build(root, monkeypatch)
    prs = nodes_of(graph, "PullRequest")
    assert set(prs) == {"PR-5", "PR-6"}
    assert prs["PR-5"].props["title"] == "Add the feature" and prs["PR-5"].props["state"] == "merged"
    assert prs["PR-5"].props["head"] == "feature-x" and prs["PR-5"].props["merge_style"] == "merge"
    assert prs["PR-5"].props["url"] == "https://github.com/acme/widgets/pull/5" and prs["PR-5"].props["merged_at"]
    assert prs["PR-6"].props["title"] == "Fix the parser" and prs["PR-6"].props["merge_style"] == "squash"
    merges = edges_of(graph, "MERGES")
    assert {d for (s, d) in merges if s == "PR-5"} == {sha["merge"], sha["first"], sha["second"]}, "the merge commit and what it brought in"
    assert {d for (s, d) in merges if s == "PR-6"} == {sha["squash"]}
    assert {(e.source, e.confidence) for e in merges.values() if e.src == "PR-5"} == {("git-merge-subject", 0.9)}
    assert merges[("PR-6", sha["squash"])].source == "git-squash-subject" and merges[("PR-6", sha["squash"])].confidence == 0.9


def test_offline_closing_keywords_give_unverified_closes_at_0_7_and_a_bare_hash_gives_nothing(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    graph, _ = run_build(root, monkeypatch)
    closes = edges_of(graph, "CLOSES")
    assert set(closes) == {("PR-5", "GH-7"), ("PR-6", "GH-8")}
    for e in closes.values():
        assert e.confidence == 0.7 and e.source == "git-closing-keyword" and e.extra == {"unverified": True}
    gh = nodes_of(graph, "Ticket")
    assert gh["GH-7"].props["unverified"] is True and "title" not in gh["GH-7"].props
    assert not [e for e in graph.edges("REFERENCES") if e.dst.startswith("GH-")], "offline, '#7' in a message is not linked"


def test_a_repository_without_pull_request_subjects_gets_no_new_nodes(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.py").write_text("x = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Revert \"thing (#12)\"")
    graph, summary = pull_requests.extract(root)
    assert list(graph.nodes()) == [] and summary["pull_requests"] == 0


def test_no_network_by_default_even_with_a_github_remote(tmp_path, monkeypatch):
    root, _ = make_repo(tmp_path)
    graph, out = run_build(root, monkeypatch)       # the autouse fixture makes any request or connect raise
    assert json.loads((out / "manifest.json").read_text())["github"]["enabled"] is False
    assert not (out / "github").exists(), "no cache is written when the layer is off"
    assert graph.node_count() > 0


# ── the online layer ───────────────────────────────────────────────────────────────────────────────────────────
def test_online_issues_become_tickets_with_type_epic_and_sub_issue_links(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    t = nodes_of(graph, "Ticket")
    assert {"GH-7", "GH-8", "GH-9"} <= set(t) and "GH-5" not in t, "a pull request is not an issue"
    assert t["GH-7"].props["ticket_type"] == "BUG" and t["GH-7"].props["state"] == "closed" and t["GH-7"].props["state_reason"] == "completed"
    assert t["GH-7"].props["url"].endswith("/issues/7") and t["GH-7"].source == "github-issues" and "unverified" not in t["GH-7"].props
    assert t["GH-8"].props["ticket_type"] == "EPIC" and t["GH-8"].props["milestone"] == "v1" and t["GH-8"].props["has_sub_issues"] is True
    assert t["GH-9"].props["ticket_type"] == "FEATURE"
    child = edges_of(graph, "CHILD_OF")[("GH-9", "GH-8")]
    assert child.source == "github-sub-issues" and child.confidence == 1.0


def test_ticket_type_comes_from_the_issue_type_then_labels_then_issue():
    tt = pull_requests.ticket_type
    assert tt({"issue_type": "Bug", "labels": ["epic"]}) == "BUG" and tt({"issue_type": "User story"}) == "USER_STORY"
    assert tt({"labels": ["x", "Bug"]}) == "BUG" and tt({"labels": ["epic"]}) == "EPIC"
    assert tt({"labels": ["feature"]}) == tt({"labels": ["enhancement"]}) == "FEATURE" and tt({"labels": ["docs"]}) == "ISSUE"


def test_online_commit_lists_and_closing_references_replace_the_offline_guess(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    graph, _ = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    merges = edges_of(graph, "MERGES")
    assert all(e.confidence == 1.0 and e.source == "github-api" for e in merges.values())
    assert {d for (s, d) in merges if s == "PR-5"} == {sha["merge"], sha["first"], sha["second"]}
    closes = edges_of(graph, "CLOSES")
    assert set(closes) == {("PR-5", "GH-7")}, "the offline PR-6 -> GH-8 edge is contradicted by GitHub and gone; the other repository's #99 is ignored"
    assert closes[("PR-5", "GH-7")].confidence == 1.0 and closes[("PR-5", "GH-7")].source == "github-closing-references"
    assert "unverified" not in closes[("PR-5", "GH-7")].extra
    pr = nodes_of(graph, "PullRequest")
    assert set(pr) == {"PR-5", "PR-6", "PR-10"} and pr["PR-10"].props["state"] == "open" and pr["PR-5"].props["base"] == "main"
    assert pr["PR-5"].props["labels"] == ["enhancement"] and pr["PR-5"].props["merge_style"] == "merge"


def test_online_a_hash_mention_of_an_issue_gives_references_at_0_8(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    graph, _ = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    refs = {(e.src, e.dst): e for e in graph.edges("REFERENCES") if e.dst.startswith("GH-")}
    assert refs[(sha["mention"], "GH-7")].confidence == 0.8 and refs[(sha["mention"], "GH-7")].source == "git-hash-mention"
    assert not [k for k in refs if k[1] in ("GH-5", "GH-6")], "a pull request number is never an issue link"


def test_the_config_file_turns_the_layer_on_without_the_flag(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    (root / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    assert github_config(root) == {"enabled": True, "authors": False}
    fake = FakeGitHub(sha)
    graph, out = run_build(root, monkeypatch, fake)
    assert fake.calls["issues"] == 1 and "GH-7" in nodes_of(graph, "Ticket")
    assert github_config(tmp_path) == {"enabled": False, "authors": False}


def test_a_rebuild_fetches_only_what_changed(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    monkeypatch.setattr(github_api, "PAGE", 2)
    fake = FakeGitHub(sha)
    _, out = run_build(root, monkeypatch, fake, github=True)
    assert fake.calls["issues"] == 3 and fake.calls["pulls"] == 2, "4 issue rows (one a pull request) at 2 per page, then an empty page"
    assert {p.name for p in (out / "github").iterdir()} == {"issues.json", "pulls.json", "links.json"}
    before = dict(fake.calls)
    graph, _ = run_build(root, monkeypatch, fake, github=True)
    assert fake.calls["issues"] - before["issues"] == 1 and fake.calls["pulls"] - before["pulls"] == 1, "stopped at the first unchanged item"
    assert fake.calls["graphql"] - before["graphql"] == 1 and "GH-8" in nodes_of(graph, "Ticket"), "the cache supplies the rest"
    fake.issues[0] = issue(9, "Sub task renamed", "2026-04-01T00:00:00Z", labels=[{"name": "enhancement"}])
    graph, _ = run_build(root, monkeypatch, fake, github=True)
    assert nodes_of(graph, "Ticket")["GH-9"].props["title"] == "Sub task renamed"


# ── when GitHub cannot be reached ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", ["unreachable", "rate-limited"])
def test_an_unreachable_api_leaves_a_complete_offline_build_and_says_what_is_missing(tmp_path, monkeypatch, capsys, kind):
    root, sha = make_repo(tmp_path)
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha, fail=kind), github=True)
    assert {"PR-5", "PR-6"} == set(nodes_of(graph, "PullRequest")) and edges_of(graph, "CLOSES")
    gh = json.loads((out / "manifest.json").read_text())["github"]
    assert gh["enabled"] is True and gh["complete"] is False and any(kind in e for e in gh["errors"])
    assert f"github: issues: {kind}" in capsys.readouterr().err
    api = answer_api(root, monkeypatch)
    assert "requested but incomplete" in api.call("pull_request", number=5)["hosting"] and kind in api.call("pull_request", number=5)["hosting"]


def test_a_failed_refresh_still_uses_what_the_cache_holds(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha, fail="unreachable"), github=True)
    assert "GH-7" in nodes_of(graph, "Ticket") and ("PR-5", "GH-7") in edges_of(graph, "CLOSES")
    assert json.loads((out / "manifest.json").read_text())["github"]["complete"] is False


def test_without_a_token_only_issues_and_pull_requests_are_read_and_the_manifest_says_so(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    monkeypatch.setattr(github_api, "find_token", lambda host: None)
    fake = FakeGitHub(sha)
    monkeypatch.setattr(github_api, "http_request", lambda url, token, body=None: fake(url, "test-token", body))
    graph, out = run_build(root, monkeypatch, None, github=True)
    assert fake.calls["graphql"] == 0 and "GH-7" in nodes_of(graph, "Ticket")
    assert any("GITHUB_TOKEN" in e for e in json.loads((out / "manifest.json").read_text())["github"]["errors"])
    assert ("PR-6", "GH-8") in edges_of(graph, "CLOSES"), "no closing record fetched, so the offline guess stays (unverified)"


def test_a_repository_without_a_github_remote_skips_the_online_layer(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path, remote=None)
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    gh = json.loads((out / "manifest.json").read_text())["github"]
    assert gh["skipped"] and set(nodes_of(graph, "PullRequest")) == {"PR-5", "PR-6"}


def test_remote_urls_are_parsed():
    p = github_api.parse_remote
    assert p("git@github.com:acme/widgets.git") == ("github.com", "acme", "widgets")
    assert p("https://github.com/acme/widgets") == ("github.com", "acme", "widgets")
    assert p("ssh://git@ghe.example.com:22/acme/widgets.git") == ("ghe.example.com", "acme", "widgets")
    assert p("/local/path") is None and github_api.api_base("ghe.example.com") == "https://ghe.example.com/api/v3"


# ── privacy ────────────────────────────────────────────────────────────────────────────────────────────────────
def _store_text(out: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in sorted(out.rglob("*")) if p.is_file() and p.suffix in (".json", ".jsonl"))


def test_no_description_login_or_email_reaches_the_store_unless_authors_is_enabled(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    _, out = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    text = _store_text(out)
    assert SECRET not in text, "descriptions are parsed for references and dropped (the squash body and the API body)"
    assert "mallory" not in text and "dev@example.com" not in text
    for line in (out / "nodes.jsonl").read_text().splitlines():
        n = json.loads(line)
        if n["type"] == "PullRequest" or n["natural_key"].startswith("GH-"):
            assert "author" not in n["properties"] and "octocat" not in line, n
    for line in (out / "edges.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["verb"] in ("MERGES", "CLOSES"):
            assert "octocat" not in line


def test_authors_are_stored_only_on_opt_in_and_a_cache_written_with_them_is_scrubbed_after(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    assert nodes_of(graph, "PullRequest")["PR-5"].props["author"] == "mallory" and nodes_of(graph, "Ticket")["GH-7"].props["author"] == "mallory"
    assert SECRET not in _store_text(out)
    offline, _ = pull_requests.extract(root, None, authors=True)
    assert nodes_of(offline, "PullRequest")["PR-5"].props["author"] == "octocat", "offline: the head owner from the merge subject"
    (root / "devkb.json").write_text(json.dumps({"github": {"authors": False}}))
    graph, out = run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    assert "mallory" not in (out / "nodes.jsonl").read_text() and "mallory" not in (out / "github" / "issues.json").read_text() \
        or not (out / "github" / "issues.json").exists()
    assert "author" not in nodes_of(graph, "PullRequest")["PR-5"].props


# ── tools and packs ────────────────────────────────────────────────────────────────────────────────────────────
def answer_api(root: Path, monkeypatch):
    ctx = resolve(str(root))
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("TST", telemetry=False)


def test_tools_follow_merges_and_closes(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    api = answer_api(root, monkeypatch)
    pr = api.call("pull_request", number="#5")
    assert pr["id"] == "PR-5" and pr["state"] == "merged" and pr["n_commits"] == 3 and pr["merge_style"] == "merge"
    assert pr["closes"] == [{"id": "GH-7"}] and pr["links"] == {"commits": "github-api", "closes": "github-api"}
    assert "GitHub's own record" in pr["hosting"] and "error" in api.call("pull_request", number=999)
    tr = api.call("trace", ticket="GH-7")
    assert tr["type"] == "BUG" and tr["pull_requests"][0]["id"] == "PR-5" and "hosting" in tr
    ln = api.call("lineage", ticket="GH-7")
    assert ln["commits"] >= 3 and ln["pull_requests"][0]["id"] == "PR-5"
    assert api.call("lineage", ticket="GH-9")["parent_issue"] == ["GH-8"] and api.call("lineage", ticket="GH-8")["sub_issues"] == ["GH-9"]
    rp = api.call("review_pack", rev=sha["squash"])
    assert rp["pull_requests"] == ["PR-6"] and "hosting" in rp
    rp5 = api.call("review_pack", rev=sha["merge"])
    assert rp5["pull_requests"] == ["PR-5"] and "GH-7" in rp5["tickets"]
    h = api.call("history", files=["app.py"])["commits"]
    assert any(c.get("pr") == ["PR-5"] and c.get("closes") == ["GH-7"] for c in h) and any(c.get("pr") == ["PR-6"] for c in h)


def test_offline_answers_say_what_they_rest_on(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch)
    api = answer_api(root, monkeypatch)
    pr = api.call("pull_request", number=6)
    assert pr["closes"] == [{"id": "GH-8", "unverified": True}] and "git alone" in pr["hosting"] and "--github" in pr["hosting"]
    tr = api.call("trace", ticket="GH-8")
    assert "unverified" in tr and tr["pull_requests"][0]["id"] == "PR-6"


def test_the_pr_pack_lists_commits_functions_tests_and_closed_issues(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    pack = Packer(answer_api(root, monkeypatch)).pr("5")
    assert pack.startswith("# Graph pack: pull request #5 (Add the feature)")
    assert "## Commits it merged (3; links from github-api)" in pack and "add feature" in pack
    assert "`app.py::feature`" in pack and "tests/test_feature.py" in pack
    assert "## Issues it closes (links from github-api)" in pack and "`GH-7` Crash on start" in pack
    assert "GitHub's own record" in pack and "unverified" not in pack
    assert "has no pull request 77" in Packer(answer_api(root, monkeypatch)).pr("77")


def test_the_pr_pack_marks_links_the_offline_layer_could_not_verify(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch)
    api = answer_api(root, monkeypatch)
    pack = Packer(api).pr("6")
    assert "(1; links from git-subject)" in pack and "`app.py::parse`" in pack
    assert "`GH-8`" in pack and "**unverified**" in pack and "git alone" in pack
    ticket = Packer(api).ticket("GH-8")
    assert "**Unverified:**" in ticket and "## Pull requests closing it (1)" in ticket and "`PR-6`" in ticket and "Fix the parser" in ticket


def test_the_ticket_pack_for_a_hosted_issue_goes_through_its_pull_requests(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch, FakeGitHub(sha), github=True)
    pack = Packer(answer_api(root, monkeypatch)).ticket("GH-7")
    assert "## Pull requests closing it (1)" in pack and "`PR-5` merged Add the feature" in pack
    assert "`app.py::feature`" in pack and "tests/test_feature.py" in pack and "GitHub's own record" in pack


def test_the_cli_pack_command_takes_ticket_and_pr(tmp_path, monkeypatch, capsys):
    root, sha = make_repo(tmp_path)
    run_build(root, monkeypatch)
    from devkb import packs  # noqa: PLC0415
    ctx = resolve(str(root))
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    monkeypatch.setattr(sys, "argv", ["packs", "--project", "TST", "pr", "5"])
    assert packs.main() == 0
    assert "Graph pack: pull request #5" in capsys.readouterr().out


def test_epics_query_alias_includes_issues_with_sub_issues():
    import inspect
    from devkb import query
    assert "has_sub_issues" in inspect.getsource(query)


def test_the_build_flag_reaches_both_build_steps():
    from devkb import cli
    src = (_REPO_ROOT / "devkb/build_symbols.py").read_text()
    assert '"--github"' in src and '"--github"' in (_REPO_ROOT / "devkb/build.py").read_text()
    assert "--github" in cli.__doc__
