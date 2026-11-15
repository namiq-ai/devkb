"""ADR-DEVKB-007: pull requests and hosted issues join the graph.

Every repository here is a throwaway git repository built by the fixture, and the GitHub API is a function that
answers from a table: no test touches the network (a guard fails the test that tries).
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build, build_symbols, cli, github, model, packs, process_api  # noqa: E402
from devkb.extractors import members, pull_requests  # noqa: E402

LOGIN = "zz-secret-login"
BODY = "zz-secret-description-text"
REVIEW = "zz-secret-review-text"
EMAIL = "zz-secret@example.net"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _commit(root: Path, subject: str, *more: str) -> str:
    args = ["commit", "-qa", "-m", subject]
    for m in more:
        args += ["-m", m]
    git(root, *args)
    return git(root, "rev-parse", "HEAD")


def _append(root: Path, text: str) -> None:
    with open(root / "pkg" / "widget.py", "a") as fh:
        fh.write(text)


class Repo(type(Path())):
    """A path that also carries the commit ids of the history built in it."""
    shas: dict


@pytest.fixture
def repo(tmp_path):
    """main: initial; PR 1 merged with a merge commit (two feature commits); PR 2 squashed ("Closes #8", "Fixes #4");
    PR 3 rebased (two commits, no trace in the subjects); a plain commit mentioning #7."""
    root = Repo(tmp_path / "widgets")
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Tess Tester")
    git(root, "remote", "add", "origin", "https://github.com/acme/widgets.git")
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "widget.py").write_text("def make():\n    return 1\n")
    (root / "tests" / "test_widget.py").write_text(
        "from pkg import widget\n\ndef test_make():\n    widget.make()\n\ndef test_extra():\n    widget.extra()\n\n"
        "def test_squashed():\n    widget.squashed()\n")
    git(root, "add", "-A")
    shas = {"initial": _commit(root, "initial")}
    git(root, "checkout", "-q", "-b", "feature-a")
    _append(root, "\ndef extra():\n    return 2\n")
    shas["f1"] = _commit(root, "Add extra widget", "Fixes #7")
    _append(root, "\ndef polish():\n    return 3\n")
    shas["f2"] = _commit(root, "Polish extra")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "feature-a", "-m", "Merge pull request #1 from acme/feature-a", "-m", "Add extra widget")
    shas["merge"] = git(root, "rev-parse", "HEAD")
    _append(root, "\ndef squashed():\n    return 4\n")
    shas["squash"] = _commit(root, "Improve widget (#2)", "Closes #8\nFixes #4")
    _append(root, "\ndef tweak_a():\n    return 5\n")
    shas["r1"] = _commit(root, "Tweak A")
    _append(root, "\ndef tweak_b():\n    return 6\n")
    shas["r2"] = _commit(root, "Tweak B")
    _append(root, "\ndef tail():\n    return 7\n")
    shas["mention"] = _commit(root, "Note about #7 in passing")
    root.shas = shas
    return root


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A test that reaches for the network fails instead of making a request."""
    def refuse(*a, **kw):
        raise AssertionError("the network was used")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setattr(github, "find_token", lambda host="github.com": "t0ken")


# ── the mocked API ───────────────────────────────────────────────────────────
def make_api(repo: Path, fail=None):
    """A transport answering from tables. `fail(method, url)` may return a (status, headers, payload) or raise."""
    s = repo.shas
    pulls = [
        {"number": 4, "title": "A draft", "state": "open", "merged_at": None, "updated_at": "2026-01-04T00:00:00Z",
         "base": {"ref": "main"}, "head": {"ref": "draft"}, "labels": [], "html_url": "https://github.com/acme/widgets/pull/4",
         "user": {"login": LOGIN}, "body": BODY, "merge_commit_sha": None},
        {"number": 3, "title": "Tweaks", "state": "closed", "merged_at": "2026-01-03T00:00:00Z", "updated_at": "2026-01-03T00:00:00Z",
         "base": {"ref": "main"}, "head": {"ref": "tweaks"}, "labels": [{"name": "chore"}], "user": {"login": LOGIN}, "body": BODY,
         "html_url": "https://github.com/acme/widgets/pull/3", "merge_commit_sha": s["r2"]},
        {"number": 2, "title": "Improve widget", "state": "closed", "merged_at": "2026-01-02T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
         "base": {"ref": "main"}, "head": {"ref": "improve"}, "labels": [], "user": {"login": LOGIN}, "body": BODY,
         "html_url": "https://github.com/acme/widgets/pull/2", "merge_commit_sha": s["squash"]},
        {"number": 1, "title": "Add extra widget", "state": "closed", "merged_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
         "base": {"ref": "main"}, "head": {"ref": "feature-a"}, "labels": [{"name": "feature"}], "user": {"login": LOGIN}, "body": BODY,
         "html_url": "https://github.com/acme/widgets/pull/1", "merge_commit_sha": s["merge"]},
    ]
    commits = {
        1: [s["f1"], s["f2"]],
        2: ["a" * 40],                      # the squashed branch's own commit: not in this repository
        3: ["b" * 40, "c" * 40],            # rebased: neither original is in this repository
        4: [],
    }
    subjects = {3: ["Tweak A", "Tweak B"]}
    closing = {1: [7], 2: [], 3: [], 4: []}
    issues = [
        {"number": 10, "title": "Child of the epic", "state": "open", "labels": [], "created_at": "2026-01-01", "updated_at": "2026-01-10T00:00:00Z",
         "html_url": "https://github.com/acme/widgets/issues/10", "user": {"login": LOGIN}, "body": BODY,
         "parent_issue_url": "https://api.github.com/repos/acme/widgets/issues/9", "type": {"name": "Task"}},
        {"number": 9, "title": "The epic", "state": "open", "labels": [{"name": "planning"}], "created_at": "2026-01-01",
         "updated_at": "2026-01-09T00:00:00Z", "html_url": "https://github.com/acme/widgets/issues/9", "user": {"login": LOGIN},
         "sub_issues_summary": {"total": 1}},
        {"number": 8, "title": "Wish", "state": "open", "labels": [{"name": "enhancement"}], "created_at": "2026-01-01",
         "updated_at": "2026-01-08T00:00:00Z", "html_url": "https://github.com/acme/widgets/issues/8", "user": {"login": LOGIN}},
        {"number": 7, "title": "Crash on start", "state": "closed", "state_reason": "completed", "labels": [{"name": "bug"}],
         "milestone": {"title": "v1"}, "created_at": "2026-01-01", "closed_at": "2026-01-02", "updated_at": "2026-01-07T00:00:00Z",
         "html_url": "https://github.com/acme/widgets/issues/7", "user": {"login": LOGIN}, "body": BODY},
        {"number": 4, "title": "A draft", "state": "open", "pull_request": {"url": "x"}, "labels": [], "updated_at": "2026-01-04T00:00:00Z",
         "user": {"login": LOGIN}},
        {"number": 5, "title": "Plain", "state": "open", "labels": [], "created_at": "2026-01-01", "updated_at": "2026-01-05T00:00:00Z",
         "html_url": "https://github.com/acme/widgets/issues/5"},
    ]
    log: list[tuple[str, str]] = []

    def page(items, url):
        q = dict(p.split("=") for p in url.split("?", 1)[1].split("&")) if "?" in url else {}
        n, per = int(q.get("page", 1)), int(q.get("per_page", 100))
        return items[(n - 1) * per:n * per]

    def transport(method, url, headers, body):
        log.append((method, url))
        if fail:
            r = fail(method, url)
            if r is not None:
                return r
        path = url.split("api.github.com", 1)[1] if "api.github.com" in url else url
        base = path.split("?")[0]
        if method == "POST":
            q = json.loads(body)["query"]
            import re
            nums = [int(x) for x in re.findall(r"pullRequest\(number: (\d+)\)", q)]
            repo_ = {f"p{n}": {"closingIssuesReferences": {"nodes": [
                {"number": i, "repository": {"nameWithOwner": "acme/widgets"}} for i in closing[n]] +
                ([{"number": 99, "repository": {"nameWithOwner": "other/elsewhere"}}] if n == 1 else [])}} for n in nums}
            return 200, {}, {"data": {"repository": repo_}}
        if base == "/repos/acme/widgets/pulls":
            return 200, {}, page(pulls, url)
        if base == "/repos/acme/widgets/issues":
            return 200, {}, page(issues, url)
        if base.endswith("/commits"):
            n = int(base.split("/")[-2])
            subs = subjects.get(n, [""] * len(commits[n]))
            return 200, {}, [{"sha": sha, "commit": {"message": f"{sub}\n\n{REVIEW}", "author": {"email": EMAIL}}}
                             for sha, sub in zip(commits[n], subs)]
        if base.endswith("/sub_issues"):
            return 200, {}, [{"number": 10}]
        return 404, {}, {"message": "Not Found"}

    transport.log = log
    return transport


def run_build(repo: Path, monkeypatch=None, *, on=True, transport=None, **kw):
    client = github.Client(github.parse_remote("https://github.com/acme/widgets.git"), "t", transport or make_api(repo)) if on else None
    graph, store = build.build(str(repo), github=on or None, github_client=client, **kw)
    return graph, store, client


def edges(graph, verb):
    return {(e.src, e.dst): e for e in graph.edges(verb)}


# ── ontology ─────────────────────────────────────────────────────────────────
def test_the_node_type_and_the_two_verbs_are_registered_and_a_member_prefixes_them():
    assert "PullRequest" in model.NODE_TYPES and {"MERGES", "CLOSES"} <= set(model.VERBS)
    assert members._prefixed("LIB", "PullRequest", "PR-5") == "LIB:PR-5"
    assert members._prefixed("LIB", "Ticket", "GH-5") == "LIB:GH-5"


# ── offline layer ────────────────────────────────────────────────────────────
def test_offline_merge_commit_gives_merges_to_the_merge_and_to_the_commits_it_brought_in(repo):
    graph, _, _ = run_build(repo, on=False)
    s = repo.shas
    pr = {n.natural_key: n for n in graph.nodes("PullRequest")}["PR-1"]
    assert pr.props["number"] == 1 and pr.props["state"] == "merged" and pr.props["merge_style"] == "merge"
    assert pr.props["title"] == "Add extra widget" and pr.props["head"] == "feature-a"
    assert pr.props["url"] == "https://github.com/acme/widgets/pull/1"
    m = edges(graph, "MERGES")
    assert {dst for (src, dst) in m if src == "PR-1"} == {s["merge"], s["f1"], s["f2"]}
    e = m[("PR-1", s["f1"])]
    assert (e.source, e.confidence) == ("git-merge-subject", 0.9)
    assert s["initial"] not in {dst for (src, dst) in m if src == "PR-1"}


def test_offline_squash_commit_gives_merges_to_that_commit_only(repo):
    graph, _, _ = run_build(repo, on=False)
    s = repo.shas
    pr = {n.natural_key: n for n in graph.nodes("PullRequest")}["PR-2"]
    assert pr.props["merge_style"] == "squash" and pr.props["title"] == "Improve widget"
    m = edges(graph, "MERGES")
    assert {dst for (src, dst) in m if src == "PR-2"} == {s["squash"]}
    assert (m[("PR-2", s["squash"])].source, m[("PR-2", s["squash"])].confidence) == ("git-squash-subject", 0.9)
    assert "PR-3" not in {n.natural_key for n in graph.nodes("PullRequest")}, "a rebase merge leaves no trace in git"


def test_offline_closing_keywords_give_unverified_closes_at_0_7_and_a_bare_mention_gives_nothing(repo):
    graph, _, _ = run_build(repo, on=False)
    c = edges(graph, "CLOSES")
    # PR 1's branch commit says "Fixes #7"; PR 2's squash commit says "Closes #8" and "Fixes #4"
    assert set(c) == {("PR-1", "GH-7"), ("PR-2", "GH-8"), ("PR-2", "GH-4")}
    for e in c.values():
        assert (e.source, e.confidence, e.extra) == ("git-closing-keyword", 0.7, {"unverified": True})
    stubs = {n.natural_key: n for n in graph.nodes("Ticket")}
    assert stubs["GH-7"].props == {"unverified": True}
    assert not list(graph.edges("REFERENCES")), "offline, a bare #7 in a commit message makes no edge"


def test_a_repository_without_a_hosting_remote_gets_no_pull_requests(repo):
    git(repo, "remote", "remove", "origin")
    graph, store, _ = run_build(repo, on=False)
    assert not list(graph.nodes("PullRequest")) and not list(graph.edges("MERGES"))
    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["github"]["remote"] is None


def test_a_local_path_remote_is_not_a_hosting_remote(repo):
    git(repo, "remote", "set-url", "origin", "/srv/git/widgets.git")
    graph, _, _ = run_build(repo, on=False)
    assert not list(graph.nodes("PullRequest"))


def test_closing_keyword_for_another_repository_or_the_pr_itself_is_ignored():
    assert pull_requests._closing_numbers("Fixes other/place#3 and closes #4, resolved: #5, see #6", "acme/widgets") == [4, 5]
    assert pull_requests._closing_numbers("fixes acme/widgets#9", "acme/widgets") == [9]


def test_parse_remote_forms():
    assert github.parse_remote("git@github.com:acme/widgets.git").slug == "acme/widgets"
    assert github.parse_remote("ssh://git@ghe.example.org/acme/widgets").api == "https://ghe.example.org/api/v3"
    assert github.parse_remote("https://github.com/acme/widgets/").host == "github.com"
    assert github.parse_remote("../widgets") is None


# ── no network unless asked ──────────────────────────────────────────────────
def test_a_build_with_a_github_remote_and_no_flag_makes_no_request_and_looks_for_no_token(repo, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("looked for a token / made a client")
    monkeypatch.setattr(github, "find_token", boom)
    monkeypatch.setattr(github, "make_client", boom)
    real = subprocess.run
    seen = []

    def spy(cmd, *a, **kw):
        seen.append(list(cmd))
        return real(cmd, *a, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    graph, store = build.build(str(repo))
    assert list(graph.nodes("PullRequest"))
    assert not any(c[0] == "gh" for c in seen)
    assert not (store / "github").exists()
    assert json.loads((store / "manifest.json").read_text())["github"]["online"] is None


def test_the_config_file_turns_the_online_layer_on(repo, monkeypatch):
    (repo / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    transport = make_api(repo)
    monkeypatch.setattr(github, "make_client", lambda root, remote=None: github.Client(remote, "t", transport))
    graph, store = build.build(str(repo))
    assert transport.log and {n.natural_key for n in graph.nodes("PullRequest")} >= {"PR-3", "PR-4"}
    assert (store / "github" / "pulls.json").exists()


def test_the_build_flag_reaches_both_build_steps_from_the_cli(repo, monkeypatch):
    transport = make_api(repo)
    monkeypatch.setattr(github, "make_client", lambda root, remote=None: github.Client(remote, "t", transport))
    assert cli.main(["build", "--project", str(repo), "--github"]) == 0
    assert transport.log and (repo / ".devkb" / "github" / "status.json").exists()


# ── online layer ─────────────────────────────────────────────────────────────
def test_online_commit_lists_are_confidence_1_and_cover_a_rebase_merge(repo):
    graph, _, _ = run_build(repo)
    s = repo.shas
    prs = {n.natural_key: n for n in graph.nodes("PullRequest")}
    assert set(prs) == {"PR-1", "PR-2", "PR-3", "PR-4"}
    assert prs["PR-3"].props["merge_style"] == "rebase" and prs["PR-3"].props["state"] == "merged"
    assert prs["PR-4"].props["state"] == "open" and prs["PR-1"].props["labels"] == ["feature"]
    assert prs["PR-1"].props["base"] == "main"
    m = edges(graph, "MERGES")
    assert m[("PR-3", s["r2"])].confidence == 1.0 and m[("PR-3", s["r2"])].source == "github-pr-merge-commit"
    assert m[("PR-1", s["f1"])].confidence == 1.0 and m[("PR-1", s["f1"])].source == "github-pr-commits"
    assert m[("PR-1", s["merge"])].confidence == 1.0, "confirmed by the API's merge commit: the 0.9 edge is replaced"
    assert len([k for k in m if k[0] == "PR-1"]) == 3
    assert not any(dst in ("a" * 40, "b" * 40) for (_s, dst) in m), "an API commit that is not in this repository makes no edge"


def test_online_closes_replaces_the_guess_and_removes_what_the_api_contradicts(repo):
    graph, _, _ = run_build(repo)
    c = edges(graph, "CLOSES")
    assert set(c) == {("PR-1", "GH-7")}, "the API says PR 1 closes 7 (and an issue of another repository, ignored); 2 closes nothing"
    assert (c[("PR-1", "GH-7")].source, c[("PR-1", "GH-7")].confidence, c[("PR-1", "GH-7")].extra) == ("github-closing-references", 1.0, {})
    keys = {n.natural_key: n for n in graph.nodes("Ticket")}
    assert "GH-4" not in keys, "#4 is a pull request, not an issue: the unverified stub is removed"
    assert "unverified" not in keys["GH-7"].props and "unverified" not in keys["GH-8"].props


def test_hosted_issues_are_tickets_with_type_state_and_sub_issue_edges(repo):
    graph, _, _ = run_build(repo)
    t = {n.natural_key: n for n in graph.nodes("Ticket")}
    assert {"GH-5", "GH-7", "GH-8", "GH-9", "GH-10"} <= set(t) and "GH-4" not in t
    assert t["GH-7"].source == "github-issues"
    assert t["GH-7"].props["ticket_type"] == "BUG" and t["GH-8"].props["ticket_type"] == "FEATURE"
    assert t["GH-5"].props["ticket_type"] == "ISSUE" and t["GH-10"].props["ticket_type"] == "TASK"
    assert t["GH-7"].props["state"] == "closed" and t["GH-7"].props["state_reason"] == "completed"
    assert t["GH-7"].props["milestone"] == "v1" and t["GH-7"].props["closed_at"] == "2026-01-02"
    assert t["GH-7"].props["url"] == "https://github.com/acme/widgets/issues/7" and t["GH-7"].props["labels"] == ["bug"]
    assert t["GH-9"].props["has_sub_issues"] is True
    co = edges(graph, "CHILD_OF")
    assert set(co) == {("GH-10", "GH-9")}
    assert (co[("GH-10", "GH-9")].source, co[("GH-10", "GH-9")].confidence) == ("github-sub-issues", 1.0)


def test_an_issue_type_beats_a_label_and_labels_map_to_ticket_types():
    f = pull_requests.ticket_type_of
    assert f({"type": "Bug", "labels": ["epic"]}) == "BUG"
    assert f({"labels": ["Epic"]}) == "EPIC" and f({"labels": ["type: bug"]}) == "BUG"
    assert f({"labels": ["feature"]}) == "FEATURE" and f({"labels": ["docs"]}) == "ISSUE" and f({"type": "Spike"}) == "SPIKE"


def test_a_commit_mentioning_an_issue_references_it_once_the_online_layer_knows_it_is_an_issue(repo):
    graph, _, _ = run_build(repo)
    s = repo.shas
    r = edges(graph, "REFERENCES")
    e = r[(s["mention"], "GH-7")]
    assert (e.source, e.confidence) == ("git-hash-mention", 0.8)
    assert (s["f1"], "GH-7") in r, "'Fixes #7' also mentions it"
    assert not any(dst in ("GH-4", "GH-1", "GH-2") for (_src, dst) in r), "a pull request number is not a ticket"


def test_the_epic_alias_includes_an_issue_with_sub_issues(repo):
    from devkb import query
    _, store, _ = run_build(repo)
    from devkb.index import load
    idx = load(store)
    spec = {"uid": "s", "type": "Spec", "natural_key": "docs/s.md", "source": "t", "properties": {}}
    idx.by_uid["s"] = spec
    idx.by_natural_key[("Spec", "docs/s.md")] = spec
    for t in ("GH-9", "GH-8"):
        idx.in_edges["s"].append({"verb": "IMPLEMENTS", "from_uid": model.uid_for("Ticket", t), "to_uid": "s", "properties": {}})
    out = query.implementing(idx, "epics", "docs/s.md")
    assert [r["ticket_type"] for r in out["results"]] == ["ISSUE"] and out["results"][0]["spec"] == "docs/s.md"


def test_the_cache_makes_a_rebuild_fetch_only_what_changed(repo):
    first = make_api(repo)
    run_build(repo, transport=first)
    n_first = len(first.log)
    assert any("/pulls/1/commits" in u for _m, u in first.log) and any("graphql" in u for _m, u in first.log)
    second = make_api(repo)
    graph, store, _ = run_build(repo, transport=second)
    detail = [u for _m, u in second.log if "/commits" in u or "graphql" in u or "sub_issues" in u]
    assert detail == [], f"nothing changed, so only the lists are fetched: {detail}"
    assert len(second.log) < n_first and edges(graph, "CLOSES").keys() == {("PR-1", "GH-7")}
    # a pull request that changed upstream is refetched, and only it
    third = make_api(repo)
    cache = json.loads((store / "github" / "pulls.json").read_text())
    cache["items"]["1"]["updated_at"] = "2025-01-01T00:00:00Z"
    (store / "github" / "pulls.json").write_text(json.dumps(cache))
    run_build(repo, transport=third)
    assert [u for _m, u in third.log if "/commits" in u] == [u for _m, u in third.log if "/pulls/1/commits" in u] != []


# ── when GitHub cannot be reached ────────────────────────────────────────────
def test_unreachable_api_completes_with_the_offline_layer_and_says_so(repo, capsys):
    def down(method, url):
        raise github.FetchError("unreachable", "Name or service not known")
    graph, store, _ = run_build(repo, transport=make_api(repo, fail=down))
    assert {n.natural_key for n in graph.nodes("PullRequest")} == {"PR-1", "PR-2"}
    assert ("PR-1", "GH-7") in edges(graph, "CLOSES") and edges(graph, "CLOSES")[("PR-1", "GH-7")].extra == {"unverified": True}
    online = json.loads((store / "manifest.json").read_text())["github"]["online"]
    assert online["complete"] is False and any("not listed" in n for n in online["notes"])
    assert "github:" in capsys.readouterr().err


def test_rate_limit_mid_build_keeps_what_was_fetched_and_lists_what_was_not(repo):
    def limited(method, url):
        if "/pulls/2/commits" in url:
            return 403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1"}, {"message": "API rate limit exceeded"}
        return None
    graph, store, _ = run_build(repo, transport=make_api(repo, fail=limited))
    online = json.loads((store / "manifest.json").read_text())["github"]["online"]
    assert online["complete"] is False and online["n_unfetched_pulls"] >= 1
    assert any("rate-limited" in n for n in online["notes"])
    # the pull request that could not be fetched keeps its offline links, still marked unverified
    c = edges(graph, "CLOSES")
    assert ("PR-2", "GH-8") in c and c[("PR-2", "GH-8")].extra == {"unverified": True}


def test_an_old_cache_stands_in_when_the_api_goes_away(repo):
    run_build(repo)

    def down(method, url):
        raise github.FetchError("unreachable", "offline")
    graph, store, _ = run_build(repo, transport=make_api(repo, fail=down))
    online = json.loads((store / "manifest.json").read_text())["github"]["online"]
    assert online["complete"] is False and online["from_cache"] is True
    assert "PR-3" in {n.natural_key for n in graph.nodes("PullRequest")}


def test_online_without_a_hosting_remote_is_reported_not_attempted(repo):
    git(repo, "remote", "remove", "origin")
    graph, store = build.build(str(repo), github=True, github_client=None)
    online = json.loads((store / "manifest.json").read_text())["github"]["online"]
    assert online["complete"] is False and "no hosting remote" in online["notes"][0]


# ── privacy ──────────────────────────────────────────────────────────────────
def _everything_written(store: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in store.rglob("*") if p.is_file())


def test_no_description_review_text_login_or_email_is_written_by_default(repo):
    _, store, _ = run_build(repo)
    text = _everything_written(store)
    assert (store / "github" / "pulls.json").exists()
    for secret in (BODY, REVIEW, LOGIN, EMAIL):
        assert secret not in text, secret


def test_authors_opt_in_stores_the_login_and_nothing_else_private(repo):
    (repo / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    graph, store, _ = run_build(repo)
    assert {n.props.get("author") for n in graph.nodes("PullRequest")} == {LOGIN}
    assert {n.props.get("author") for n in graph.nodes("Ticket") if n.natural_key in ("GH-7", "GH-8")} == {LOGIN}
    text = _everything_written(store)
    assert LOGIN in text
    for secret in (BODY, REVIEW, EMAIL):
        assert secret not in text, secret


def test_turning_authors_off_again_discards_the_logins_already_cached(repo):
    (repo / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    run_build(repo)
    (repo / "devkb.json").write_text(json.dumps({"github": {}}))
    _, store, _ = run_build(repo)
    assert LOGIN not in _everything_written(store)


def test_only_an_exact_true_enables_the_options(repo):
    (repo / "devkb.json").write_text(json.dumps({"github": {"enabled": "yes", "authors": 1}}))
    from devkb.project_context import github_config
    assert github_config(repo) == {"enabled": False, "authors": False}


# ── tools and packs ──────────────────────────────────────────────────────────
@pytest.fixture
def served(repo):
    build_symbols.build(str(repo))
    run_build(repo)
    return process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)


@pytest.fixture
def served_offline(repo):
    build_symbols.build(str(repo))
    run_build(repo, on=False)
    return process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)


def test_trace_and_lineage_follow_closes_and_merges(served, repo):
    t = served.call("trace", ticket="GH-7")
    assert t["closed_by"] == [{"pr": "PR-1", "state": "merged", "title": "Add extra widget", "closes": ["GH-7"]}]
    assert t["coverage"] == {"complete": True}
    la = served.call("lineage", ticket="GH-7")
    assert la["pull_requests"][0]["pr"] == "PR-1"
    assert la["commits"] >= 3, "the commits of the pull request that closes it, and the commit that mentions it"
    epic = served.call("trace", ticket="GH-9")
    assert epic["children"] == ["GH-10"]


def test_history_names_the_pull_request_a_commit_came_in_with(served):
    r = served.call("history", files=["pkg/widget.py"], limit=20)
    by_subject = {c["s"]: c for c in r["commits"]}
    assert by_subject["Improve widget (#2)"]["pr"] == ["PR-2"]
    assert by_subject["Add extra widget"]["pr"] == ["PR-1"]
    assert "coverage" in r


def test_review_pack_names_the_pull_request_and_the_issues_it_closes(served, repo):
    r = served.call("review_pack", rev=repo.shas["merge"])
    assert [p["pr"] for p in r["pull_requests"]] == ["PR-1"]
    assert "GH-7" in r["tickets"]
    assert "pkg/widget.py::extra" in r["changed_symbols"]


def test_offline_answers_say_what_the_offline_layer_cannot_see(served_offline):
    t = served_offline.call("trace", ticket="GH-7")
    assert t["closed_by"][0]["closes"] == ["GH-7?"], "a '?' marks a link the offline layer could not verify"
    note = t["coverage"]["note"]
    assert t["coverage"]["complete"] is False
    assert "rebase merges are invisible" in note and "unverified" in note


def test_an_answer_after_a_failed_online_build_says_github_could_not_be_read(repo):
    def down(method, url):
        raise github.FetchError("unreachable", "no route")
    build_symbols.build(str(repo))
    run_build(repo, transport=make_api(repo, fail=down))
    api = process_api.ProcessAPI(str(repo), use_cache=False, telemetry=False)
    note = api.call("trace", ticket="GH-7")["coverage"]["note"]
    assert "GitHub could not be read in full" in note and "no route" in note


def test_a_graph_without_pull_requests_answers_exactly_as_before(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "a.py").write_text("def f():\n    return 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "ODSF-1: first")
    build_symbols.build(str(root))
    build.build(str(root))
    api = process_api.ProcessAPI(str(root), use_cache=False, telemetry=False)
    assert "coverage" not in api.call("history", files=["a.py"])
    assert "coverage" not in api.call("review_pack", rev="HEAD")


def test_pack_pr_gives_commits_changed_functions_tests_and_closed_issues(served, repo):
    p = packs.Packer(served)
    text = p.pr("1")
    assert "# Graph pack: pull request PR-1 (Add extra widget)" in text
    assert "merged 2026-01-01, merge merge" in text
    assert "## Commits it brought in (3)" in text and "git-merge-subject" not in text  # online: 1.0 edges note their source
    assert "`pkg/widget.py::extra`" in text
    assert "`tests/test_widget.py`" in text and "Run: `python3 -m pytest tests/test_widget.py -q`" in text
    assert "`GH-7`" in text and "unverified" not in text
    assert "**Pull-request links complete.**" in text
    assert p.pr("PR-1") == text


def test_pack_pr_offline_marks_unverified_links_and_states_the_coverage(served_offline):
    text = packs.Packer(served_offline).pr("2")
    assert "`pkg/widget.py::squashed`" in text
    assert "`GH-8`" in text and "**unverified**" in text
    assert "(git-squash-subject, 0.9)" in text
    assert "**Pull-request links incomplete:**" in text and "rebase merges are invisible" in text


def test_pack_pr_unknown_number_says_so(served):
    assert "has no pull request PR-99" in packs.Packer(served).pr("99")


def test_pack_ticket_lists_the_pull_requests_that_close_it(served):
    text = packs.Packer(served).ticket("GH-7")
    assert "## Pull requests that close it (1)" in text and "`PR-1` merged: Add extra widget" in text
    assert "`pkg/widget.py::extra`" in text and "`tests/test_widget.py`" in text
    assert "**Pull-request links complete.**" in text


def test_the_pack_command_line_accepts_ticket_and_pr(served, repo, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["packs", "--project", str(repo), "pr", "2"])
    assert packs.main() == 0
    assert "pull request PR-2" in capsys.readouterr().out
