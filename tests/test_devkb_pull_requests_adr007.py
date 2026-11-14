"""ADR-DEVKB-007: pull requests and hosted issues join the graph.

Every test builds a fixture git repository. The GitHub API is a fake `github.transport`; no test touches the network
(a fixture makes any socket connection fail the test).
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build as build_mod, build_symbols, github, packs, process_api  # noqa: E402
from devkb.extractors import pull_requests  # noqa: E402
from devkb.model import NODE_TYPES, VERBS  # noqa: E402

SECRET_BODY = "SECRET-BODY-TEXT-rotate-the-key"
LOGIN = "octo-login-xyz"
EMAIL = "someone@secret.example"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(github, "find_token", lambda host: "test-token")


def _git(root: Path, *args: str, date: str | None = None) -> str:
    env = {**({"GIT_COMMITTER_DATE": date} if date else {}), "GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.com", "GIT_COMMITTER_NAME": "Dev",
           "GIT_COMMITTER_EMAIL": "dev@example.com", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(root)}
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text)


@pytest.fixture
def repo(tmp_path):
    """main: initial; PR 5 merged with a merge commit (closes 7); PR 6 squashed ("Closes #8, #9"); PR 14 squashed
    ("Fixes #5", a pull request); a bare mention of #11; a rebase-merged change no subject names."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "pkg/core.py", "def save(x):\n    return x\n\ndef load():\n    return 0\n")
    _write(root, "pkg/cache.py", "def warm():\n    return 1\n")
    _write(root, "tests/test_core.py", "from pkg.core import save\n\ndef test_save():\n    assert save(1) == 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Initial import")
    _git(root, "checkout", "-q", "-b", "feature-a")
    _write(root, "pkg/core.py", "def save(x):\n    return x + 1\n\ndef load():\n    return 0\n")
    _git(root, "commit", "-qam", "Make save add one")
    _write(root, "pkg/core.py", "def save(x):\n    return x + 1\n\ndef load():\n    return 5\n")
    _git(root, "commit", "-qam", "Teach load a value", "-m", "Fixes #7")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "feature-a", "-m", "Merge pull request #5 from acme/feature-a", "-m", "Add loader")
    _write(root, "pkg/core.py", "def save(x):\n    return x + 2\n\ndef load():\n    return 5\n")
    _git(root, "commit", "-qam", "Rework save (#6)", "-m", "Closes #8, #9")
    _write(root, "pkg/cache.py", "def warm():\n    return 2\n")
    _git(root, "commit", "-qam", "Tidy the cache, see #11")
    _write(root, "pkg/cache.py", "def warm():\n    return 3\n")
    _git(root, "commit", "-qam", "Cleanup (#14)", "-m", "Fixes #5")
    _write(root, "pkg/cache.py", "def warm():\n    return 4\n")
    _git(root, "commit", "-qam", "Warm the cache earlier")  # rebase-merged PR 12: no subject names it
    return root


def _with_remote(root: Path) -> None:
    _git(root, "remote", "add", "origin", "https://github.com/acme/widgets.git")


def _sha(root: Path, subject_start: str) -> str:
    return _git(root, "log", "--all", "--format=%H", f"--grep=^{subject_start}").splitlines()[0]


def _graph(repo: Path, **kw):
    g, _ = pull_requests.extract(_ctx(repo), github.Options(**kw))
    return g


def _ctx(repo: Path):
    from devkb.project_context import resolve
    return resolve(str(repo))


def _edges(g, verb):
    return {(e.src, e.dst): e for e in g.edges(verb)}


def _node(g, typ, key):
    return next((n for n in g.nodes(typ) if n.natural_key == key), None)


# ── the offline layer ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_ontology_names_the_new_type_and_verbs():
    assert "PullRequest" in NODE_TYPES and {"MERGES", "CLOSES"} <= set(VERBS)
    text = (_REPO_ROOT / "devkb" / "ontology.md").read_text()
    assert "`PullRequest`" in text and "`MERGES`" in text and "`CLOSES`" in text and "GH-" in text


def test_a_merge_commit_gives_a_pull_request_merging_the_merge_commit_and_the_commits_it_brought_in(repo, monkeypatch):
    monkeypatch.setenv("DEVKB_DIR", str(repo.parent / "kb"))
    g = _graph(repo)
    pr = _node(g, "PullRequest", "PR-5")
    assert pr.props["state"] == "merged" and pr.props["merge_style"] == "merge" and pr.props["head"] == "feature-a"
    assert pr.props["title"] == "Add loader" and pr.props["merged_at"]
    merges = _edges(g, "MERGES")
    merge_sha = _sha(repo, "Merge pull request #5")
    brought = {_sha(repo, "Make save add one"), _sha(repo, "Teach load a value")}
    assert {dst for (src, dst) in merges if src == "PR-5"} == {merge_sha} | brought
    assert all(e.confidence == 0.9 and e.source == "git-merge-subject" for (s, _), e in merges.items() if s == "PR-5")


def test_a_squash_subject_gives_a_pull_request_merging_that_commit(repo):
    g = _graph(repo)
    pr = _node(g, "PullRequest", "PR-6")
    assert pr.props["merge_style"] == "squash" and pr.props["title"] == "Rework save" and pr.props["state"] == "merged"
    e = _edges(g, "MERGES")[("PR-6", _sha(repo, "Rework save"))]
    assert e.confidence == 0.9 and e.source == "git-squash-subject"
    assert _node(g, "PullRequest", "PR-12") is None, "a rebase merge leaves no trace in git"


def test_the_pull_request_url_comes_from_the_origin_remote(repo):
    assert "url" not in _node(_graph(repo), "PullRequest", "PR-6").props
    _with_remote(repo)
    assert _node(_graph(repo), "PullRequest", "PR-6").props["url"] == "https://github.com/acme/widgets/pull/6"


def test_a_closing_keyword_gives_an_unverified_closes_at_0_7_and_a_bare_mention_gives_nothing(repo):
    g = _graph(repo)
    closes = _edges(g, "CLOSES")
    assert set(closes) == {("PR-5", "GH-7"), ("PR-6", "GH-8"), ("PR-6", "GH-9"), ("PR-14", "GH-5")}
    for e in closes.values():
        assert e.confidence == 0.7 and e.source == "git-closing-keyword" and e.extra == {"unverified": True}
    assert _node(g, "Ticket", "GH-7").props["unverified"] is True
    assert list(g.edges("REFERENCES")) == [], "offline, a bare #N cannot be told from a pull request"
    assert _node(g, "Ticket", "GH-11") is None


def test_a_pull_requests_own_number_and_other_repositories_are_not_closing_targets(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "a.py", "x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Init")
    _git(root, "remote", "add", "origin", "git@github.com:acme/widgets.git")
    _write(root, "a.py", "x = 2\n")
    _git(root, "commit", "-qam", "Change (#20)", "-m", "Fixes #20, fixes other/repo#3 and acme/widgets#4; resolves #5 and #6")
    closes = set(_edges(_graph(root), "CLOSES"))
    assert closes == {("PR-20", "GH-4"), ("PR-20", "GH-5"), ("PR-20", "GH-6")}


def test_a_repository_without_pull_request_subjects_gets_no_new_nodes(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "a.py", "x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Init with issue-123 and v2.0 (final)")
    g = _graph(root)
    assert not list(g.nodes()) and not list(g.edges())


def test_a_backport_with_the_same_number_does_not_add_a_second_merged_commit(repo):
    _git(repo, "checkout", "-q", "-b", "release", "HEAD~4")
    _write(repo, "pkg/cache.py", "def warm():\n    return 9\n")
    _git(repo, "commit", "-qam", "Rework save (#6)", date="2099-01-01T00:00:00+0000")
    merges = [dst for (src, dst) in _edges(_graph(repo), "MERGES") if src == "PR-6"]
    assert merges == [_git(repo, "log", "-1", "--format=%H", "main", "--grep=^Rework save")], "the earlier commit is the pull request's"


# ── the fake GitHub ──────────────────────────────────────────────────────────────────────────────────────────────
def _issue(n, title, state="closed", labels=(), **extra):
    return {"number": n, "title": title, "state": state, "state_reason": "completed" if state == "closed" else None,
            "labels": [{"name": l} for l in labels], "milestone": {"title": "v1"}, "html_url": f"https://github.com/acme/widgets/issues/{n}",
            "created_at": "2026-01-01T00:00:00Z", "closed_at": "2026-02-01T00:00:00Z" if state == "closed" else None,
            "updated_at": f"2026-03-{n:02d}T00:00:00Z", "body": SECRET_BODY, "user": {"login": LOGIN, "email": EMAIL}, **extra}


def _pull(n, title, merged, sha=None, head="topic", updated=None):
    return {"number": n, "title": title, "state": "closed" if merged else "open", "merged_at": "2026-03-01T00:00:00Z" if merged else None,
            "base": {"ref": "main"}, "head": {"ref": head}, "labels": [{"name": "ready"}], "merge_commit_sha": sha,
            "html_url": f"https://github.com/acme/widgets/pull/{n}", "updated_at": updated or f"2026-03-{n:02d}T12:00:00Z",
            "body": SECRET_BODY, "user": {"login": LOGIN}}


class FakeGitHub:
    """Answers the few endpoints the sync reads. `calls` records every request as (method, path, query)."""

    def __init__(self, repo: Path) -> None:
        sha = lambda s: _sha(repo, s)  # noqa: E731
        self.issues = [
            _issue(5, "Add loader", pull_request={"url": "x"}), _issue(6, "Rework save", pull_request={"url": "x"}),
            _issue(7, "Load returns nothing", labels=["bug"]),
            _issue(8, "Faster save", labels=["enhancement"], parent_issue_url="https://api.github.com/repos/acme/widgets/issues/9"),
            _issue(9, "Save rework", type={"name": "Epic"}, sub_issues_summary={"total": 1, "completed": 1}),
            _issue(11, "Cache is cold", state="open", labels=["question"]),
        ]
        self.pulls = [_pull(5, "Add loader", True, sha("Merge pull request #5"), "feature-a"),
                      _pull(6, "Rework save", True, sha("Rework save")),
                      _pull(12, "Warm the cache earlier", True, sha("Warm the cache earlier")),
                      _pull(13, "Draft idea", False), _pull(14, "Cleanup", True, sha("Cleanup (#14)"))]
        self.commits = {5: [sha("Make save add one"), sha("Teach load a value")], 6: ["f" * 40], 12: [sha("Warm the cache earlier")],
                        14: [sha("Cleanup (#14)")]}
        self.closing = {5: [7], 6: [8], 12: [], 13: [], 14: []}
        self.calls: list[tuple[str, str, dict]] = []
        self.fail: Exception | None = None
        self.rate_limit_on: str | None = None

    def __call__(self, method, url, headers, body):
        if self.fail:
            raise self.fail
        parsed = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        path = parsed.path
        self.calls.append((method, path, q))
        assert "Authorization" not in headers or headers["Authorization"] == "Bearer test-token"
        if self.rate_limit_on and self.rate_limit_on in path:
            return 403, {"x-ratelimit-remaining": "0"}, {"message": "API rate limit exceeded"}
        if method == "POST":
            return 200, {}, {"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
                {"number": n, "updatedAt": next(p["updated_at"] for p in self.pulls if p["number"] == n),
                 "closingIssuesReferences": {"nodes": [{"number": i, "repository": {"nameWithOwner": "acme/widgets"}} for i in nums]}}
                for n, nums in sorted(self.closing.items(), reverse=True)]}}}}
        if path.endswith("/issues"):
            since = q.get("since", "")
            return 200, {}, [i for i in sorted(self.issues, key=lambda i: i["updated_at"], reverse=True) if i["updated_at"] >= since]
        if path.endswith("/pulls"):
            return 200, {}, sorted(self.pulls, key=lambda p: p["updated_at"], reverse=True)
        if path.endswith("/commits"):
            n = int(path.split("/")[-2])
            return 200, {}, [{"sha": s, "commit": {"message": SECRET_BODY}, "author": {"login": LOGIN}} for s in self.commits[n]]
        raise AssertionError(f"unexpected request {method} {path}")


@pytest.fixture
def gh(repo, monkeypatch):
    _with_remote(repo)
    fake = FakeGitHub(repo)
    monkeypatch.setattr(github, "transport", fake)
    return fake


def _build(repo: Path, monkeypatch, *, flag=True):
    kb = repo.parent / "kb"
    monkeypatch.setenv("DEVKB_DIR", str(kb))
    build_symbols.build(str(repo))
    graph, _ = build_mod.build(str(repo), use_github=flag)
    return graph, kb


# ── the online layer ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_online_layer_adds_pull_requests_issues_and_confirmed_links(repo, gh):
    g = _graph(repo, enabled=True)
    states = {n.natural_key: n.props["state"] for n in g.nodes("PullRequest")}
    assert states == {"PR-5": "merged", "PR-6": "merged", "PR-12": "merged", "PR-13": "open", "PR-14": "merged"}
    assert _node(g, "PullRequest", "PR-5").props["base"] == "main" and _node(g, "PullRequest", "PR-5").props["labels"] == ["ready"]
    # tickets: GH-<n>, ticket_type from the issue type, else labels, else ISSUE
    kinds = {n.natural_key: n.props["ticket_type"] for n in g.nodes("Ticket")}
    assert kinds == {"GH-7": "BUG", "GH-8": "FEATURE", "GH-9": "EPIC", "GH-11": "ISSUE"}
    t7 = _node(g, "Ticket", "GH-7")
    assert t7.source == "github-issues" and t7.props["state"] == "closed" and t7.props["milestone"] == "v1" and t7.props["state_reason"] == "completed"
    assert t7.props["url"].endswith("/issues/7") and t7.props["created_at"] and t7.props["closed_at"]
    child = _edges(g, "CHILD_OF")
    assert set(child) == {("GH-8", "GH-9")} and child[("GH-8", "GH-9")].source == "github-sub-issues"
    assert _node(g, "Ticket", "GH-9").props["epic"] is True


def test_online_merges_and_closes_replace_what_the_offline_layer_guessed(repo, gh):
    g = _graph(repo, enabled=True)
    closes = _edges(g, "CLOSES")
    assert set(closes) == {("PR-5", "GH-7"), ("PR-6", "GH-8")}, "GH-9 is contradicted, GH-5 is a pull request"
    assert all(e.confidence == 1.0 and e.source == "github-closing-references" and not e.extra for e in closes.values())
    merges = _edges(g, "MERGES")
    merge_sha = _sha(repo, "Merge pull request #5")
    assert {d for (s, d) in merges if s == "PR-5"} == {merge_sha, _sha(repo, "Make save add one"), _sha(repo, "Teach load a value")}
    assert merges[("PR-5", merge_sha)].confidence == 1.0 and merges[("PR-5", merge_sha)].source == "github-pr-commits"
    # a rebase merge, invisible offline, is found through the pull request's commit list
    assert ("PR-12", _sha(repo, "Warm the cache earlier")) in merges
    assert not [e for (s, d), e in merges.items() if e.confidence < 1.0]


def test_a_commit_mentioning_an_issue_references_it_only_online(repo, gh):
    refs = _edges(_graph(repo, enabled=True), "REFERENCES")
    sha = _sha(repo, "Tidy the cache")
    assert (sha, "GH-11") in refs and refs[(sha, "GH-11")].confidence == 0.8 and refs[(sha, "GH-11")].source == "git-hash-mention"
    assert not [k for k in refs if k[1] in ("GH-5", "GH-6")], "a mention of a pull request is not a ticket link"


def test_a_rebuild_fetches_only_what_changed(repo, gh):
    _graph(repo, enabled=True)
    first = len(gh.calls)
    assert first >= 6
    gh.calls.clear()
    g = _graph(repo, enabled=True)
    assert [c for c in gh.calls if c[1].endswith("/commits")] == [], "no pull request changed, so no commit list is refetched"
    issue_calls = [c for c in gh.calls if c[1].endswith("/issues")]
    assert issue_calls and issue_calls[0][2]["since"] == "2026-03-11T00:00:00Z"
    assert _node(g, "PullRequest", "PR-12") is not None, "served from the cache"
    gh.calls.clear()
    gh.pulls[2]["updated_at"] = "2026-04-01T00:00:00Z"
    _graph(repo, enabled=True)
    assert [c[1] for c in gh.calls if c[1].endswith("/commits")] == ["/repos/acme/widgets/pulls/12/commits"]


def test_the_cache_lives_in_the_devkb_directory_and_holds_no_text(repo, gh):
    _graph(repo, enabled=True)
    cache = repo / ".devkb" / "github" / "cache.json"
    data = json.loads(cache.read_text())
    assert set(data["issues"]) == {"7", "8", "9", "11"} and set(data["prs"]) >= {"5", "6", "12"}
    assert SECRET_BODY not in cache.read_text() and LOGIN not in cache.read_text() and EMAIL not in cache.read_text()


def test_unreachable_github_completes_with_the_offline_layer_and_says_so(repo, gh, monkeypatch, capsys):
    gh.fail = github.Unreachable("URLError: Name or service not known")
    graph, kb = _build(repo, monkeypatch)
    manifest = json.loads((kb / "manifest.json").read_text())
    assert manifest["github"]["status"] == "unreachable" and "unreachable" in " ".join(manifest["github"]["errors"])
    assert "github unreachable" in capsys.readouterr().err
    assert {n.natural_key for n in graph.nodes("PullRequest")} == {"PR-5", "PR-6", "PR-14"}
    api = process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)
    r = api.call("pull_request", number="6")
    assert r["coverage"]["complete"] is False and "unreachable" in " ".join(r["coverage"]["links"])
    assert r["closes"] and all(c["unverified"] for c in r["closes"])


def test_a_rate_limit_keeps_what_was_fetched_and_reports_the_rest(repo, gh, monkeypatch):
    gh.rate_limit_on = "/pulls/12/commits"
    graph, kb = _build(repo, monkeypatch)
    rep = json.loads((kb / "manifest.json").read_text())["github"]
    assert rep["status"] == "partial" and any("rate limit" in e for e in rep["errors"])
    assert {n.natural_key for n in graph.nodes("Ticket")} >= {"GH-7", "GH-11"}, "issues were fetched before the limit"
    cache = json.loads((repo.parent / "kb" / "github" / "cache.json").read_text())
    assert "12" not in cache["commits"], "the pull request whose commit list hit the limit is retried next build"
    gh.rate_limit_on = None
    g2, kb2 = _build(repo, monkeypatch)
    assert json.loads((kb2 / "manifest.json").read_text())["github"]["status"] == "ok"
    assert ("PR-12", _sha(repo, "Warm the cache earlier")) in _edges(g2, "MERGES")


def test_without_a_token_closing_links_stay_offline_and_unverified(repo, gh, monkeypatch):
    monkeypatch.setattr(github, "find_token", lambda host: None)
    g = _graph(repo, enabled=True)
    closes = _edges(g, "CLOSES")
    assert ("PR-5", "GH-7") in closes and closes[("PR-5", "GH-7")].confidence == 0.7
    assert not closes[("PR-5", "GH-7")].extra, "GH-7 is a known issue, so no longer unverified"
    assert ("PR-14", "GH-5") not in closes, "GH-5 is a known pull request"
    assert not [c for c in gh.calls if c[0] == "POST"]


def test_the_environment_token_is_never_sent_to_another_host(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abc")
    assert github.find_token("github.com") == "ghp_abc"
    monkeypatch.setattr(github.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(OSError("no gh")))
    assert github.find_token("git.example.com") is None


def test_remote_urls_are_parsed():
    assert github.parse_remote("https://github.com/acme/widgets.git") == ("github.com", "acme", "widgets")
    assert github.parse_remote("git@github.com:acme/widgets.git") == ("github.com", "acme", "widgets")
    assert github.parse_remote("ssh://git@ghe.corp.example:2222/acme/widgets") == ("ghe.corp.example", "acme", "widgets")
    assert github.parse_remote("/srv/git/widgets") is None
    assert github.api_base("ghe.corp.example") == "https://ghe.corp.example/api/v3"


# ── no network by default; privacy ───────────────────────────────────────────────────────────────────────────────
def test_a_build_with_a_github_remote_and_no_flag_makes_no_request(repo, monkeypatch):
    _with_remote(repo)

    def forbidden(*a, **kw):
        raise AssertionError("the default build touched the network or gh")
    monkeypatch.setattr(github, "transport", forbidden)
    monkeypatch.setattr(github, "find_token", forbidden)
    graph, kb = _build(repo, monkeypatch, flag=False)
    assert {n.natural_key for n in graph.nodes("PullRequest")} == {"PR-5", "PR-6", "PR-14"}
    assert json.loads((kb / "manifest.json").read_text())["github"]["enabled"] is False
    assert "status" not in json.loads((kb / "manifest.json").read_text())["github"]
    assert not (kb / "github").exists()


def test_devkb_json_can_turn_the_online_layer_on(repo, gh, monkeypatch):
    (repo / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    graph, kb = _build(repo, monkeypatch, flag=False)
    assert gh.calls and json.loads((kb / "manifest.json").read_text())["github"]["status"] == "ok"
    assert github.options({"github": {"enabled": True}}).enabled and not github.options({}).enabled
    assert github.options({}, flag=True).enabled


def test_no_description_review_text_author_or_email_is_written_unless_authors_is_on(repo, gh, monkeypatch):
    _, kb = _build(repo, monkeypatch)
    blob = "\n".join(p.read_text(errors="ignore") for p in kb.rglob("*") if p.is_file() and p.suffix != ".pkl")
    assert SECRET_BODY not in blob and LOGIN not in blob and EMAIL not in blob
    (repo / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    _, kb = _build(repo, monkeypatch)
    blob = "\n".join(p.read_text(errors="ignore") for p in kb.rglob("*") if p.is_file() and p.suffix != ".pkl")
    assert LOGIN in blob and SECRET_BODY not in blob and EMAIL not in blob
    nodes = [json.loads(l) for l in (kb / "nodes.jsonl").read_text().splitlines()]
    assert next(n for n in nodes if n["natural_key"] == "PR-5")["properties"]["author"] == LOGIN
    # switching authors off again also clears them from the cache
    (repo / "devkb.json").write_text(json.dumps({"github": {"authors": False}}))
    _, kb = _build(repo, monkeypatch)
    assert LOGIN not in (kb / "github" / "cache.json").read_text() and LOGIN not in (kb / "nodes.jsonl").read_text()


def test_the_build_command_line_accepts_github_in_both_steps(repo, monkeypatch):
    monkeypatch.setenv("DEVKB_DIR", str(repo.parent / "kb"))
    monkeypatch.setattr(sys, "argv", ["x", "--project", str(repo), "--github"])
    seen = []
    monkeypatch.setattr(github, "sync", lambda *a, **kw: (seen.append(1), (None, github.Report(status="unreachable", errors=["x"])))[1])
    assert build_symbols.main() == 0 and build_mod.main() == 0 and seen == [1]


# ── tools and packs ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def api(repo, gh, monkeypatch):
    _build(repo, monkeypatch)
    return process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)


def test_trace_and_lineage_follow_closes_and_merges(api, repo):
    t = api.call("trace", ticket="GH-7")
    assert t["type"] == "BUG" and t["status"] == "CLOSED"
    assert t["pull_requests"] == [{"pr": "PR-5", "title": "Add loader", "state": "merged"}] and t["coverage"]["complete"] is True
    lin = api.call("lineage", ticket="GH-7")
    assert lin["commits"] == 3 and lin["pull_requests"][0]["pr"] == "PR-5"
    epic = api.call("trace", ticket="GH-9")
    assert epic["children"] == ["GH-8"]
    ctx = api.call("sdlc_context", ticket="GH-8")
    assert ctx["commits"] == 1 and ctx["pull_requests"][0]["pr"] == "PR-6" and "core.py" in ctx["files"][0] + "".join(ctx["files"])


def test_history_names_the_pull_request_and_issue_of_each_commit(api):
    r = api.call("history", files=["pkg/core.py"])
    by_subject = {c["s"]: c for c in r["commits"]}
    assert by_subject["Rework save (#6)"]["pr"] == ["PR-6"] and by_subject["Rework save (#6)"]["t"] == ["GH-8", "GH-9"]
    assert by_subject["Teach load a value"]["t"] == ["GH-7"]


def test_review_pack_names_the_pull_requests_and_issues_of_the_range(api, repo):
    first = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    r = api.call("review_pack", rev=f"{first}..{_sha(repo, 'Rework save')}")
    assert r["pull_requests"] == ["PR-5", "PR-6"] and {"GH-7", "GH-8"} <= set(r["tickets"])
    assert "pkg/core.py::save" in r["changed_symbols"]


def test_pull_request_tool_gives_commits_changed_functions_tests_and_issues(api):
    r = api.call("pull_request", number="PR-5")
    assert r["state"] == "merged" and r["merge_style"] == "merge" and r["n_commits"] == 3
    assert r["closes"] == [{"ticket": "GH-7", "title": "Load returns nothing", "state": "closed"}]
    assert set(r["changed_symbols"]) == {"pkg/core.py::save", "pkg/core.py::load"}
    assert api.call("pull_request", number="#6")["changed_symbols"] == ["pkg/core.py::save"]
    assert "error" in api.call("pull_request", number="999")
    rebase = api.call("pull_request", number="12")
    assert rebase["n_commits"] == 1 and rebase["changed_symbols"] == ["pkg/cache.py::warm"]
    draft = api.call("pull_request", number="13")
    assert draft["state"] == "open" and draft["n_commits"] == 0 and "changed_symbols" not in draft


def test_pack_pr_lists_commits_functions_tests_and_issues(api):
    out = packs.Packer(api).pr("5")
    assert out.startswith("# Graph pack: PR-5 (Add loader)")
    assert "## Commits (3)" in out and "`GH-7` Load returns nothing" in out and "`pkg/core.py::save`" in out
    assert "tests/test_core.py" in out and "Pull-request and issue links: **complete**" in out
    assert "no pull request" in packs.Packer(api).pr("999")


def test_pack_ticket_lists_the_pull_requests_that_close_a_hosted_issue(api):
    out = packs.Packer(api).ticket("GH-8")
    assert "## Pull requests that close it (1)" in out and "`PR-6` merged: Rework save" in out and "pkg/core.py::save" in out
    assert "Pull-request and issue links: **complete**" in out


def test_offline_answers_say_which_links_the_graph_cannot_see(repo, monkeypatch):
    _with_remote(repo)
    _build(repo, monkeypatch, flag=False)
    api = process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)
    r = api.call("pull_request", number="6")
    assert r["coverage"]["complete"] is False
    text = " ".join(r["coverage"]["links"])
    assert "GitHub was not read" in text and "unverified" in text
    assert [c["unverified"] for c in r["closes"]] == [True, True]
    out = packs.Packer(api).pr("6")
    assert "**unverified**" in out and "Pull-request and issue links: **incomplete.**" in out
    assert api.call("graph_status")["pull_requests"] == 3


def test_a_graph_without_pull_requests_is_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "pkg/a.py", "def f():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "ODSF-1: first")
    monkeypatch.setenv("DEVKB_DIR", str(tmp_path / "kb"))
    build_symbols.build(str(root))
    graph, kb = build_mod.build(str(root))
    assert not list(graph.nodes("PullRequest")) and not list(graph.edges("MERGES")) and not list(graph.edges("CLOSES"))
    api = process_api.ProcessAPI(str(root), use_cache=False, telemetry=False)
    assert "pull_requests" not in api.call("graph_status")
    assert "coverage" not in api.call("history", files=["pkg/a.py"])
    assert "no pull request" in api.call("pull_request", number="1")["error"]
