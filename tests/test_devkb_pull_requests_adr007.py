"""ADR-DEVKB-007: pull requests and hosted issues join the graph.

Every repository here is a throwaway git repository built by the fixture, with an `origin` remote that is never
contacted. The GitHub API is a fake installed as `devkb.github.TRANSPORT`; nothing in this file uses the network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build, build_symbols, cli, github, process_api  # noqa: E402
from devkb.extractors import pull_requests  # noqa: E402
from devkb.model import NODE_TYPES, VERBS  # noqa: E402
from devkb.packs import Packer  # noqa: E402

LOGIN = "octocat-api"          # an author login that exists only in the fake API's answers
DESCRIPTION = "SECRET-DESCRIPTION-TEXT"
REVIEW = "SECRET-REVIEW-TEXT"
EMAIL = "someone@example.org"


def _git(root: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def _commit(root: Path, message: str, **files: str) -> str:
    for rel, text in files.items():
        rel = rel.replace("__", "/")        # pkg__b -> pkg/b.py
        path = root / (rel if "." in rel else rel + ".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main: base; PR 7 merged with a merge commit (two commits); PR 8 squash-merged; one commit mentioning #4."""
    monkeypatch.setenv("DEVKB_DIR", str(tmp_path / "kb"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    root = tmp_path / "widgets"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "remote", "add", "origin", "https://github.com/acme/widgets.git")
    _commit(root, "Initial", pkg__a="def alpha():\n    return 1\n", tests__test_a="from pkg import a\n\ndef test_alpha():\n    a.alpha()\n")
    (root / "pkg" / "__init__.py").write_text("")
    _git(root, "checkout", "-q", "-b", "feature-x")
    f1 = _commit(root, "Add beta\n\nCloses #3", pkg__b="def beta():\n    return 2\n")
    f2 = _commit(root, "Tweak beta\n\nResolves #5", pkg__b="def beta():\n    return 3\n")
    _git(root, "checkout", "-q", "main")
    _commit(root, "Main moves on", pkg__m="X = 1\n")
    _git(root, "merge", "--no-ff", "-q", "-m", "Merge pull request #7 from alice/feature-x", "-m", "Add the beta feature", "feature-x")
    merge = _git(root, "rev-parse", "HEAD")
    squash = _commit(root, "Add gamma (#8)\n\nFixes #4\n\nFixes #9", pkg__c="def gamma():\n    return 4\n")
    mention = _commit(root, "Mention #4 in passing", pkg__d="Y = 2\n")
    (root / "pkg" / "__init__.py").write_text("")
    return {"root": root, "f1": f1, "f2": f2, "merge": merge, "squash": squash, "mention": mention, "tmp": tmp_path}


# ── the fake GitHub ──────────────────────────────────────────────────────────
def _pull(n, title, state="closed", merged=True, sha=None, head="x", labels=(), updated="2026-01-01T00:00:00Z"):
    return {"number": n, "title": title, "state": state, "merged_at": "2026-01-02T00:00:00Z" if merged else None,
            "base": {"ref": "main"}, "head": {"ref": head}, "labels": [{"name": l} for l in labels],
            "html_url": f"https://github.com/acme/widgets/pull/{n}", "merge_commit_sha": sha, "updated_at": updated,
            "user": {"login": LOGIN}, "body": DESCRIPTION, "requested_reviewers": [{"login": "reviewer-login"}]}


def _issue(n, title, state="closed", updated="2026-01-01T00:00:00Z", **extra):
    return {"number": n, "title": title, "state": state, "state_reason": "completed" if state == "closed" else None,
            "labels": [{"name": l} for l in extra.pop("labels", [])], "milestone": extra.pop("milestone", None),
            "html_url": f"https://github.com/acme/widgets/issues/{n}", "created_at": "2025-12-01T00:00:00Z",
            "closed_at": "2026-01-02T00:00:00Z" if state == "closed" else None, "updated_at": updated,
            "user": {"login": LOGIN}, "body": DESCRIPTION, **extra}


class FakeGitHub:
    def __init__(self, repo):
        self.calls: list[tuple[str, str]] = []
        self.pulls = [_pull(7, "Add the beta feature", sha=repo["merge"], head="feature-x", labels=["bug"], updated="2026-01-03T00:00:00Z"),
                      _pull(8, "Add gamma", sha=repo["squash"], head="gamma"),
                      _pull(9, "Open work", state="open", merged=False),
                      _pull(10, "Abandoned", merged=False)]
        self.commits = {7: [repo["f1"], repo["f2"]], 8: ["d" * 40], 9: [], 10: []}
        self.closing = {7: [3], 8: [4], 9: [], 10: []}
        self.issues = [_issue(3, "Beta crashes", labels=["bug"], type={"name": "Bug"}),
                       _issue(4, "Gamma programme", state="open", sub_issues_summary={"total": 1, "completed": 0}, milestone={"title": "v2"}),
                       _issue(5, "Gamma docs", labels=["enhancement"], parent_issue_url="https://api.github.com/repos/acme/widgets/issues/4"),
                       _issue(6, "Plain question")]
        self.fail: Exception | None = None
        self.limit_after: int | None = None

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        if self.fail:
            raise self.fail
        if self.limit_after is not None and len(self.calls) > self.limit_after:
            return 403, {"x-ratelimit-remaining": "0"}, {"message": "API rate limit exceeded"}
        path = url.split("api.github.com", 1)[1]
        if path == "/graphql":
            query = json.loads(body)["query"]
            repo = {}
            for n, nums in self.closing.items():
                if f"p{n}:" in query:
                    repo[f"p{n}"] = {"closingIssuesReferences": {"nodes": [
                        {"number": i, "title": "t", "state": "CLOSED", "url": "u", "repository": {"nameWithOwner": "acme/widgets"}} for i in nums]}}
            return 200, {}, {"data": {"repository": repo}}
        path = path.split("?")[0]
        if path.endswith("/pulls"):
            return 200, {}, self.pulls
        if path.endswith("/issues"):  # the issues listing also returns pull requests, as GitHub does
            return 200, {}, self.issues + [{**_issue(p["number"], p["title"]), "pull_request": {}} for p in self.pulls]
        if path.endswith("/commits"):
            n = int(path.split("/")[-2])
            return 200, {}, [{"sha": s, "commit": {"message": REVIEW, "author": {"email": EMAIL}}} for s in self.commits[n]]
        return 404, {}, None


@pytest.fixture
def api_off(monkeypatch):
    """A transport that fails the test on any request: the default build must never reach for the network."""
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("the network was used")
    monkeypatch.setattr(github, "TRANSPORT", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(github, "find_token", boom)
    return calls


@pytest.fixture
def fake(repo, monkeypatch):
    f = FakeGitHub(repo)
    monkeypatch.setattr(github, "TRANSPORT", f)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    return f


def _load(kb: Path):
    nodes = [json.loads(l) for l in (kb / "nodes.jsonl").read_text().splitlines() if l]
    edges = [json.loads(l) for l in (kb / "edges.jsonl").read_text().splitlines() if l]
    key = {n["uid"]: (n["type"], n["natural_key"]) for n in nodes}
    return {(n["type"], n["natural_key"]): n for n in nodes}, [
        (e["verb"], key[e["from_uid"]][1], key[e["to_uid"]][1], e["properties"]) for e in edges if e["from_uid"] in key and e["to_uid"] in key]


def _edges(edges, verb, src=None, dst=None):
    return [e for e in edges if e[0] == verb and (src is None or e[1] == src) and (dst is None or e[2] == dst)]


def _build(repo, github_flag=False, symbols=False):
    if symbols:
        build_symbols.build(str(repo["root"]))
    build.build(str(repo["root"]), github=github_flag)
    return Path(os.environ["DEVKB_DIR"])


# ── ontology ─────────────────────────────────────────────────────────────────
def test_the_model_has_the_node_type_and_both_verbs():
    assert "PullRequest" in NODE_TYPES and {"MERGES", "CLOSES"} <= set(VERBS)


# ── the offline layer ────────────────────────────────────────────────────────
def test_merge_and_squash_subjects_give_pull_requests_and_merges_edges(repo, api_off):
    nodes, edges = _load(_build(repo))
    pr7, pr8 = nodes[("PullRequest", "PR-7")]["properties"], nodes[("PullRequest", "PR-8")]["properties"]
    assert (pr7["number"], pr7["state"], pr7["merge_style"], pr7["head"], pr7["title"]) == (7, "merged", "merge", "feature-x", "Add the beta feature")
    assert pr7["url"] == "https://github.com/acme/widgets/pull/7" and pr7["merged_at"]
    assert (pr8["merge_style"], pr8["title"]) == ("squash", "Add gamma")
    merged7 = {e[2]: e[3] for e in _edges(edges, "MERGES", "PR-7")}
    assert set(merged7) == {repo["merge"], repo["f1"], repo["f2"]}          # the merge commit and what it brought in
    assert all(p["confidence"] == 0.9 and p["source"] == "git-merge-subject" for p in merged7.values())
    merged8 = _edges(edges, "MERGES", "PR-8")
    assert [(e[2], e[3]["source"], e[3]["confidence"]) for e in merged8] == [(repo["squash"], "git-squash-subject", 0.9)]


def test_offline_closing_keywords_give_unverified_closes_at_0_7(repo, api_off):
    nodes, edges = _load(_build(repo))
    closes = {(e[1], e[2]): e[3] for e in _edges(edges, "CLOSES")}
    assert set(closes) == {("PR-7", "GH-3"), ("PR-7", "GH-5"), ("PR-8", "GH-4"), ("PR-8", "GH-9")}
    assert all(p["confidence"] == 0.7 and p["unverified"] is True and p["source"] == "git-closing-keyword" for p in closes.values())
    assert nodes[("Ticket", "GH-3")]["properties"]["unverified"] is True


def test_offline_a_bare_hash_mention_makes_no_edge(repo, api_off):
    _, edges = _load(_build(repo))
    assert not [e for e in _edges(edges, "REFERENCES") if e[2].startswith("GH-")]


def test_building_with_a_github_remote_and_no_flag_makes_no_request(repo, api_off):
    kb = _build(repo)
    assert api_off == []
    assert not (kb / "github").exists()
    assert "github" not in json.loads((kb / "manifest.json").read_text())


def test_a_repository_without_pull_requests_gets_no_new_nodes(tmp_path, monkeypatch, api_off):
    monkeypatch.setenv("DEVKB_DIR", str(tmp_path / "kb"))
    root = tmp_path / "plain"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _commit(root, "Fix a thing (see #12)", a="x = 1\n")
    nodes, edges = _load(_build({"root": root}))
    assert not [k for k in nodes if k[0] == "PullRequest"] and not _edges(edges, "MERGES") and not _edges(edges, "CLOSES")


def test_nothing_but_the_allowed_properties_is_stored_on_a_pull_request(repo, api_off):
    nodes, _ = _load(_build(repo))
    allowed = {"number", "title", "state", "merged_at", "base", "head", "labels", "url", "merge_style"}
    for key, n in nodes.items():
        if key[0] == "PullRequest":
            assert set(n["properties"]) <= allowed, n["properties"]


# ── the online layer ─────────────────────────────────────────────────────────
def test_online_commit_lists_replace_offline_merges_at_confidence_1(repo, fake):
    nodes, edges = _load(_build(repo, github_flag=True))
    merged7 = {e[2]: e[3] for e in _edges(edges, "MERGES", "PR-7")}
    assert set(merged7) == {repo["merge"], repo["f1"], repo["f2"]}
    assert all(p["confidence"] == 1.0 and p["source"] == "github-api" for p in merged7.values())
    assert [e[3]["confidence"] for e in _edges(edges, "MERGES", "PR-8")] == [1.0]   # the squash sha comes from merge_commit_sha
    assert ("PullRequest", "PR-9") in nodes and nodes[("PullRequest", "PR-9")]["properties"]["state"] == "open"
    assert nodes[("PullRequest", "PR-10")]["properties"]["state"] == "closed"
    assert nodes[("PullRequest", "PR-7")]["properties"]["labels"] == ["bug"]
    assert nodes[("PullRequest", "PR-7")]["properties"]["base"] == "main"


def test_online_closing_records_confirm_replace_and_remove_offline_closes(repo, fake):
    nodes, edges = _load(_build(repo, github_flag=True))
    closes = {(e[1], e[2]): e[3] for e in _edges(edges, "CLOSES")}
    assert set(closes) == {("PR-7", "GH-3"), ("PR-8", "GH-4")}            # GH-5 contradicted, GH-9 is a pull request
    assert all(p["confidence"] == 1.0 and not p.get("unverified") and p["source"] == "github-closing-references" for p in closes.values())
    assert not nodes[("Ticket", "GH-3")]["properties"].get("unverified")
    assert ("Ticket", "GH-9") not in nodes


def test_hosted_issues_are_tickets_with_type_state_and_sub_issue_edges(repo, fake):
    nodes, edges = _load(_build(repo, github_flag=True))
    t3, t4, t5, t6 = (nodes[("Ticket", f"GH-{n}")]["properties"] for n in (3, 4, 5, 6))
    assert nodes[("Ticket", "GH-3")]["source"] == "github-issues"
    assert (t3["ticket_type"], t3["state"], t3["state_reason"], t3["labels"], t3["closed_at"]) == ("BUG", "closed", "completed", ["bug"], "2026-01-02T00:00:00Z")
    assert t3["url"] == "https://github.com/acme/widgets/issues/3" and t3["created_at"]
    assert (t4["ticket_type"], t4["milestone"], t4["state"]) == ("EPIC", "v2", "open")   # it has sub-issues
    assert t5["ticket_type"] == "FEATURE" and t6["ticket_type"] == "ISSUE"             # label `enhancement`, then no hint
    child = _edges(edges, "CHILD_OF", "GH-5", "GH-4")
    assert len(child) == 1 and child[0][3]["source"] == "github-sub-issues"
    assert ("Ticket", "GH-10") not in nodes and ("Ticket", "GH-7") not in nodes     # pull requests listed as issues are skipped


def test_hosted_ticket_type_rules():
    t = pull_requests.hosted_ticket_type
    assert t("Bug", [], False) == "BUG" and t("Epic", [], False) == "EPIC" and t("Task", ["bug"], False) == "TASK"
    assert t(None, ["Bug"], False) == "BUG" and t(None, ["type: bug"], False) == "BUG" and t(None, ["kind/epic"], False) == "EPIC"
    assert t(None, ["enhancement"], False) == "FEATURE" and t(None, ["feature"], False) == "FEATURE"
    assert t(None, ["docs"], False) == "ISSUE" and t(None, ["docs"], True) == "EPIC"


def test_online_a_resolved_hash_mention_references_the_issue(repo, fake):
    _, edges = _load(_build(repo, github_flag=True))
    refs = _edges(edges, "REFERENCES", repo["mention"], "GH-4")
    assert len(refs) == 1 and refs[0][3]["source"] == "git-hash-mention" and refs[0][3]["confidence"] == 0.8
    assert not _edges(edges, "REFERENCES", dst="GH-9") and not [e for e in _edges(edges, "REFERENCES") if e[2] in ("GH-7", "GH-8")]


def test_flag_or_devkb_json_turns_the_online_layer_on(repo, fake):
    (repo["root"] / "devkb.json").write_text(json.dumps({"github": {"enabled": True}}))
    _git(repo["root"], "add", "-A")
    kb = _build(repo)                                                            # no flag
    assert fake.calls and json.loads((kb / "manifest.json").read_text())["github"]["status"] == "complete"


def test_the_cache_makes_a_rebuild_fetch_only_what_changed(repo, fake):
    kb = _build(repo, github_flag=True)
    first = len(fake.calls)
    assert first > 4 and {p.name for p in (kb / "github").iterdir()} >= {"pulls.json", "issues.json", "meta.json"}
    fake.calls.clear()
    _build(repo, github_flag=True)
    assert [u.split("/repos/acme/widgets/")[1].split("?")[0] for _, u in fake.calls] == ["pulls", "issues"]   # two listing pages, no detail
    fake.pulls[0] = _pull(7, "Add the beta feature (renamed)", sha=repo["merge"], head="feature-x", updated="2026-02-01T00:00:00Z")
    fake.calls.clear()
    nodes, _ = _load(_build(repo, github_flag=True))
    paths = [u.split("/repos/acme/widgets/")[-1].split("?")[0] if "graphql" not in u else "graphql" for _, u in fake.calls]
    assert "pulls/7/commits" in paths and "graphql" in paths and not any(p in paths for p in ("pulls/8/commits", "pulls/9/commits"))
    assert nodes[("PullRequest", "PR-7")]["properties"]["title"] == "Add the beta feature (renamed)"


# ── when GitHub cannot be reached ────────────────────────────────────────────
def test_an_unreachable_api_completes_the_build_with_the_offline_layer_and_says_so(repo, fake, capsys):
    fake.fail = urllib.error.URLError("no route to host")
    kb = _build(repo, github_flag=True)
    err = capsys.readouterr().err
    nodes, edges = _load(kb)
    manifest = json.loads((kb / "manifest.json").read_text())["github"]
    assert manifest["status"] == "unreachable" and manifest["problems"] and "unreachable" in manifest["problems"][0]
    assert "could not fetch" in err and "unreachable" in err
    assert ("PullRequest", "PR-7") in nodes and _edges(edges, "MERGES", "PR-7")                  # offline layer intact
    assert {e[3]["confidence"] for e in _edges(edges, "CLOSES")} == {0.7}


def test_a_rate_limit_keeps_what_was_fetched_and_reports_partial(repo, fake):
    fake.limit_after = 2                                  # the two listings succeed, the commit lists do not
    kb = _build(repo, github_flag=True)
    nodes, edges = _load(kb)
    g = json.loads((kb / "manifest.json").read_text())["github"]
    assert g["status"] == "partial" and any("rate limit" in p for p in g["problems"])
    assert ("Ticket", "GH-3") in nodes and nodes[("Ticket", "GH-3")]["source"] == "github-issues"
    assert all(e[3]["confidence"] == 0.9 for e in _edges(edges, "MERGES", "PR-7"))               # not contradicted, not upgraded


def test_without_a_token_closing_records_are_reported_missing(repo, fake, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setattr(github, "find_token", lambda host: None)
    kb = _build(repo, github_flag=True)
    g = json.loads((kb / "manifest.json").read_text())["github"]
    assert g["status"] == "partial" and any("token" in p for p in g["problems"])
    assert not any("graphql" in u for _, u in fake.calls)
    _, edges = _load(kb)
    assert {(e[1], e[2]) for e in _edges(edges, "CLOSES")} >= {("PR-7", "GH-3"), ("PR-7", "GH-5")}   # offline links stand
    assert not [e for e in _edges(edges, "CLOSES") if e[2] == "GH-9"]                              # but GH-9 is known to be a pull request


def test_a_remote_that_is_not_github_is_reported_and_not_contacted(repo, fake):
    _git(repo["root"], "remote", "set-url", "origin", "https://gitlab.example.net/acme/widgets.git")
    kb = _build(repo, github_flag=True)
    assert fake.calls == [] and json.loads((kb / "manifest.json").read_text())["github"]["status"] == "unavailable"


def test_remote_urls_parse():
    assert github.parse_remote("git@github.com:acme/widgets.git") == ("github.com", "acme", "widgets")
    assert github.parse_remote("https://token@github.com/acme/widgets") == ("github.com", "acme", "widgets")
    assert github.parse_remote("ssh://git@github.example.com:2222/acme/widgets.git") == ("github.example.com", "acme", "widgets")
    assert github.parse_remote("not a url") is None


# ── privacy ──────────────────────────────────────────────────────────────────
def _everything_written(kb: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in kb.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".md", ".txt", ""))


def test_no_description_review_login_or_email_is_written_by_default(repo, fake):
    kb = _build(repo, github_flag=True)
    blob = _everything_written(kb)
    assert fake.calls and (kb / "github" / "pulls.json").exists()
    for secret in (DESCRIPTION, REVIEW, EMAIL, LOGIN, "reviewer-login"):
        assert secret not in blob, secret


def test_the_author_login_is_stored_only_when_authors_is_enabled(repo, fake):
    (repo["root"] / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    kb = _build(repo, github_flag=True)
    nodes, _ = _load(kb)
    assert nodes[("PullRequest", "PR-7")]["properties"]["author"] == LOGIN and nodes[("Ticket", "GH-3")]["properties"]["author"] == LOGIN
    blob = _everything_written(kb)
    assert DESCRIPTION not in blob and REVIEW not in blob and EMAIL not in blob            # authors opts in to logins only


def test_a_cache_written_without_logins_is_not_reused_once_authors_is_enabled(repo, fake):
    kb = _build(repo, github_flag=True)
    assert LOGIN not in (kb / "github" / "pulls.json").read_text()
    (repo["root"] / "devkb.json").write_text(json.dumps({"github": {"authors": True}}))
    fake.calls.clear()
    _build(repo, github_flag=True)
    assert len(fake.calls) > 2                                                             # refetched, not read from the old cache
    assert LOGIN in (kb / "github" / "pulls.json").read_text()


def test_devkb_init_gitignores_the_github_cache(repo):
    from devkb import init  # noqa: PLC0415
    root = repo["root"]
    init.run(root, "lean", hooks=False, dry_run=False)
    cache = root / ".devkb" / "github"
    cache.mkdir(parents=True)
    (cache / "pulls.json").write_text("{}")
    assert subprocess.run(["git", "check-ignore", "-q", ".devkb/github/pulls.json"], cwd=root).returncode == 0


# ── tools and packs ──────────────────────────────────────────────────────────
@pytest.fixture
def served(repo, fake):
    kb = _build(repo, github_flag=True, symbols=True)
    return process_api.ProcessAPI(str(repo["root"]), use_cache=False, telemetry=False, devkb_dir=kb)


def test_trace_follows_closes_for_a_ticket_and_describes_a_pull_request(served, repo):
    r = served.call("trace", ticket="GH-3")
    assert [p["id"] for p in r["pull_requests"]] == ["PR-7"] and "pull_requests" in r["coverage"]
    pr = served.call("trace", ticket="PR-7")
    assert pr["pull_request"] == "PR-7" and pr["n_commits"] == 3 and pr["closes"] == [{"id": "GH-3", "confidence": 1.0}]
    assert pr["merge_style"] == "merge" and pr["commit_link_confidence"] == 1.0


def test_lineage_counts_the_commits_of_the_pull_requests_that_close_the_ticket(served, repo):
    r = served.call("lineage", ticket="GH-3")
    assert r["commits"] == 3 and r["pull_requests"][0]["id"] == "PR-7"
    assert served.call("lineage", ticket="GH-4")["sub_issues"] == ["GH-5"]
    assert served.call("lineage", ticket="GH-4")["pull_requests"][0]["id"] == "PR-8"


def test_history_names_the_pull_request_of_each_commit(served):
    rows = served.call("history", files=["pkg/b.py"])["commits"]
    assert rows and all(row["pr"] == ["PR-7"] for row in rows)


def test_review_pack_lists_the_pull_requests_and_the_issues_they_close(served, repo):
    r = served.call("review_pack", rev=repo["f1"])
    assert r["pull_requests"] == [{"id": "PR-7", "title": "Add the beta feature", "state": "merged", "merge_style": "merge", "closes": [{"id": "GH-3", "confidence": 1.0}]}]
    assert "GH-3" in r["tickets"] and "pull_requests" in r["coverage"]


def test_the_ticket_pack_lists_pull_requests_commits_functions_and_tests(served):
    out = Packer(served).ticket("GH-3")
    assert "## Pull requests that close it (1)" in out and "`PR-7` merged" in out and "link confidence 1.0" in out
    assert "pkg/b.py::beta" in out and "Commits referencing it, or in a pull request that closes it (3)" in out
    assert Packer(served).ticket("3").splitlines()[0] == out.splitlines()[0]


def test_the_pr_pack_gives_commits_changed_functions_tests_and_issues(served):
    out = Packer(served).pr("7")
    assert out.startswith("# Graph pack: pull request PR-7 (Add the beta feature)")
    assert "State: merged (merge commit); main ← feature-x; merged 2026-01-02" in out
    assert "## Commits it brought in (3)" in out and "Add beta" in out and "Tweak beta" in out
    assert "`pkg/b.py::beta`" in out and "## Issues it closes (1)" in out and "`GH-3` (link confidence 1.0)" in out
    assert "read from GitHub" in out
    assert "no pull request" in Packer(served).pr("999")


def test_pack_and_coverage_say_what_the_offline_layer_could_not_verify(repo, api_off):
    kb = _build(repo, symbols=True)
    api = process_api.ProcessAPI(str(repo["root"]), use_cache=False, telemetry=False, devkb_dir=kb)
    out = Packer(api).pr("#8")
    assert "`GH-4` (link confidence 0.7, unverified)" in out and "come from git alone" in out and "closing link(s) are unverified" in out
    assert "pull_requests" in api.call("trace", ticket="GH-4")["coverage"]
    assert "unreachable" not in out


def test_an_unreachable_layer_is_stated_in_the_answer_coverage(repo, fake):
    fake.fail = urllib.error.URLError("down")
    kb = _build(repo, github_flag=True)
    api = process_api.ProcessAPI(str(repo["root"]), use_cache=False, telemetry=False, devkb_dir=kb)
    note = api.call("trace", ticket="GH-3")["coverage"]["pull_requests"]
    assert "The GitHub layer is unreachable" in note and "fall back to what git shows" in note


# ── the command line ─────────────────────────────────────────────────────────
def test_devkb_build_accepts_github_and_devkb_pack_pr_runs(repo, fake, capsys):
    assert cli.main(["build", "--project", str(repo["root"]), "--github"]) == 0
    assert fake.calls
    capsys.readouterr()
    assert cli.main(["pack", "--project", str(repo["root"]), "pr", "7"]) == 0
    assert "Graph pack: pull request PR-7" in capsys.readouterr().out
    assert cli.main(["pack", "--project", str(repo["root"]), "ticket", "GH-3"]) == 0


def test_devkb_build_without_the_flag_does_not_touch_the_network(repo, api_off):
    assert cli.main(["build", "--project", str(repo["root"])]) == 0
    assert api_off == []
