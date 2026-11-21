"""`devkb hook prompt` (devkb/router.py): a prompt is routed to the graph's answer for its SDLC stage, or to nothing."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import router  # noqa: E402

FILES = {
    "pkg/models.py": "def parse_json_string(text):\n    if not text:\n        raise ValueError('empty json payload given')\n    return text\n",
    "pkg/app.py": "from pkg.models import parse_json_string\n\n\ndef handle(raw):\n    return parse_json_string(raw)\n",
    "tests/test_app.py": "from pkg.app import handle\n\n\ndef test_handle():\n    assert handle('x') == 'x'\n",
}


def _git(root, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=root, check=True, capture_output=True)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("router")
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / ".git" / "info" / "exclude").write_text(".devkb/\n")      # the graph is not part of the repository's history
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", "."); _git(root, "commit", "-qm", "feat: parse json")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def _event(root, prompt, session="s1"):
    return {"prompt": prompt, "session_id": session, "cwd": str(root)}


# ── classification: pure ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prompt,route", [
    ("ok", "none"),
    ("please continue with the plan", "none"),
    ("Fix the crash in devkb/read_tools.py:290 when the name is empty", "located"),
    ("see devkb/hook.py line 88 for the failing branch", "located"),
    ("Traceback (most recent call last):\n  File \"a.py\", line 3, in f\nValueError: empty json payload given", "error"),
    ("users see KeyError: 'session_id' after login", "error"),
    ("work on #381 and keep the scope small", "ticket"),
    ("implement DKB-123 as written", "ticket"),
    ("apply the review feedback on #381", "change"),
    ("prepare the release and the changelog", "release"),
    ("why does parse_json_string accept empty input?", "navigate"),
    ("rename `Packer.file` to something clearer", "navigate"),
])
def test_a_prompt_is_classified_by_its_cheapest_exact_signal(prompt, route):
    assert router.classify(prompt, branch_has_diff=True).name == route


def test_a_change_request_without_a_branch_diff_is_not_a_change_route():
    assert router.classify("apply the review feedback please", branch_has_diff=False).name != "change"


def test_a_located_prompt_skips_the_graph_even_when_it_names_a_ticket_and_a_symbol():
    r = router.classify("#381: fix `parse_json_string` in pkg/models.py:3", branch_has_diff=False)
    assert r.name == "located" and router.bundle(r, Path(".")) == ("", {})


# ── bundles over a real graph ──────────────────────────────────────────────────────────────────────────────────────────
def test_navigate_gives_the_definition_line_and_never_a_body(repo):
    out = router.on_prompt(_event(repo, "why does `parse_json_string` accept empty input?"))
    text = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "pkg/models.py:1" in text and "1 caller" in text and "raise ValueError" not in text


def test_a_fuzzy_name_is_not_a_lead(repo):
    assert router.on_prompt(_event(repo, "why does `parse_jsn_strng_zzz` accept empty input?")) is None


def test_a_graph_behind_head_says_so(repo):
    (repo / "NEW.md").write_text("x"); _git(repo, "add", "."); _git(repo, "commit", "-qm", "docs: new")
    try:
        text = router.on_prompt(_event(repo, "why does `parse_json_string` accept empty input?"))["hookSpecificOutput"]["additionalContext"]
        assert "1 commits before HEAD" in text
    finally:
        _git(repo, "reset", "-q", "--hard", "HEAD~1")


def test_error_routes_to_the_raiser_and_stays_under_budget(repo):
    out = router.on_prompt(_event(repo, "Traceback (most recent call last):\nValueError: empty json payload given"))
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "pkg/models.py" in text and len(text) <= router.BUDGET + 40


def test_an_error_the_graph_does_not_know_adds_nothing(repo):
    assert router.on_prompt(_event(repo, "RuntimeError: nothing like this anywhere in this repository ever")) is None


def test_change_route_gives_the_packs_of_the_branchs_own_files(repo):
    _git(repo, "checkout", "-q", "-b", "feat/cr")
    (repo / "pkg/models.py").write_text(FILES["pkg/models.py"] + "\n\ndef extra():\n    return 1\n")
    _git(repo, "commit", "-qam", "feat: extra")
    try:
        out = router.on_prompt(_event(repo, "apply the review feedback on this branch"))
        text = out["hookSpecificOutput"]["additionalContext"]
        assert "blast radius" in text and "pkg/models.py" in text
    finally:
        _git(repo, "checkout", "-q", "main"); _git(repo, "branch", "-qD", "feat/cr")


def test_release_summarises_commits_since_the_last_tag_without_the_graph(repo):
    _git(repo, "tag", "v0.1.0")
    (repo / "NOTES.md").write_text("x"); _git(repo, "add", "."); _git(repo, "commit", "-qm", "fix(core)!: drop the old flag")
    try:
        text = router.on_prompt(_event(repo, "prepare the release"))["hookSpecificOutput"]["additionalContext"]
        assert "Since v0.1.0: 1 commits" in text and "**major**" in text
    finally:
        _git(repo, "reset", "-q", "--hard", "HEAD~1"); _git(repo, "tag", "-d", "v0.1.0")


# ── never worse than nothing ───────────────────────────────────────────────────────────────────────────────────────────
def test_no_graph_no_answer_and_no_failure(tmp_path):
    assert router.on_prompt(_event(tmp_path, "why does `parse_json_string` accept empty input?")) is None


def test_the_off_switch(repo, monkeypatch):
    monkeypatch.setenv("DEVKB_ROUTER", "0")
    assert router.on_prompt(_event(repo, "why does `parse_json_string` accept empty input?")) is None


def test_every_decision_is_logged_including_none(repo):
    log = repo / ".devkb" / "router.jsonl"
    before = len(log.read_text().splitlines()) if log.exists() else 0
    router.on_prompt(_event(repo, "thanks, that is all for now"))
    rows = [json.loads(x) for x in log.read_text().splitlines()][before:]
    assert rows and rows[-1]["route"] == "none" and rows[-1]["chars"] == 0


def test_the_cli_entry_point_prints_hook_json_and_exits_zero(repo):
    env = dict(os.environ, PYTHONPATH=str(ROOT), CLAUDE_PROJECT_DIR=str(repo))
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "hook", "prompt"], input=json.dumps(_event(repo, "why does `parse_json_string` accept empty input?")),
                       capture_output=True, text=True, env=env, cwd=repo)
    assert p.returncode == 0 and p.stdout, p.stderr
    assert "pkg/models.py:1" in json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    bad = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "hook", "prompt"], input="not json", capture_output=True, text=True, env=env, cwd=repo)
    assert bad.returncode == 0 and bad.stdout == ""


# ── findings of the workflow validation (each was a wrong or missing answer on devkb's own repository) ─────────────────────
@pytest.mark.parametrize("prompt", ["please release the lock held by the build", "the release of v2 is blocked, fix the parser"])
def test_the_word_release_alone_is_not_a_release_request(prompt):
    assert router.classify(prompt).name != "release"


def test_a_range_without_conventional_commits_gets_no_semver_verdict(repo):
    _git(repo, "tag", "v0.0.1")
    (repo / "A.md").write_text("x"); _git(repo, "add", "."); _git(repo, "commit", "-qm", "bench: something (#5)")
    try:
        text = router.release_bundle(repo)
        assert "no SemVer verdict" in text and "bump**" not in text and "bench 1" in text
    finally:
        _git(repo, "reset", "-q", "--hard", "HEAD~1"); _git(repo, "tag", "-d", "v0.0.1")


def test_a_message_that_is_returned_not_raised_gets_no_error_bundle(repo):
    # `pack error` lists loosely matched raisers for it; none of their files contains the text
    pack = "## Raised by\n- `pkg/models.py::parse_json_string` — `x`\n\n## Functions"
    assert router.error_bundle(repo, "no tracked file with symbols by that path", pack) == ""


def test_listed_raisers_that_do_not_contain_the_message_are_dropped(repo):
    pack = ("## Raised by\n- `pkg/models.py::parse_json_string` — `x`\n- `pkg/app.py::handle` — `y`\n\n"
            "## Functions that reach it\n- `other`")
    out = router.error_bundle(repo, "empty json payload given", pack)
    assert "parse_json_string" in out and "handle" not in out and "listed 2 raisers; 1 contain" in out and "## Functions" not in out


def test_navigate_finds_private_and_capitalised_names_and_lists_tests(repo, tmp_path):
    (repo / "pkg" / "store.py").write_text("class Packer:\n    def _seen(self):\n        return 1\n")
    r = router.classify("Touches the pre_edit hook and the Packer, fix _seen in it")
    assert {"Packer", "_seen"} <= set(r.subjects)
    out = router.on_prompt(_event(repo, "why does `parse_json_string` get called? the handle path"))
    assert "tests: `tests/test_app.py`" in out["hookSpecificOutput"]["additionalContext"] or "no test calls it" in out["hookSpecificOutput"]["additionalContext"]
    (repo / "pkg" / "store.py").unlink()


class _Fake:
    def __init__(self):
        self.asked = []

    def pack(self, kind, subject):
        self.asked.append(subject)
        return "# Graph pack: ticket\n\nThe graph has no ticket x. Search." if subject == "150" else "# Graph pack: ticket GH-150 ()\n\n## Commits\n- c1"


def test_a_bare_ticket_number_is_tried_as_a_github_issue():
    f = _Fake()
    text, _ = router.bundle(router.Route("ticket", "t", ["150"]), Path("."), f)
    assert f.asked == ["150", "GH-150"] and "c1" in text and "# Graph pack" not in text


def test_a_file_line_that_is_not_a_file_of_the_repository_is_not_a_location(repo):
    # #203's reproduction prints `src/a.cpp L8-10` from a fixture: the agent still has to find the code (benchmark, 2026-11-20)
    prompt = "symbol gives a merged range. Reproduce: `devkb uses area` prints src/a.cpp L8-10 and src/a.cpp L12-14; fix `parse_json_string`"
    assert router.classify(prompt).name == "located"                                 # pure: every path counts
    assert router.classify(prompt, known=lambda p: router.tracked(repo, p)).name == "navigate"
    assert router.classify("fix pkg/models.py:3", known=lambda p: router.tracked(repo, p)).name == "located"
    assert router.classify("fix models.py:3", known=lambda p: router.tracked(repo, p)).name == "located"   # a bare name of a tracked file
