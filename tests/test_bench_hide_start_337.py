"""#337: the ticket's location can be withheld from the prompt, for arms that are otherwise set up as their base arm."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")
rt = importlib.import_module("release_table")

BODY = """**Who is affected:** callers of `pack_file` in `devkb/packs.py`.

**Reproduce:**
```
devkb pack --project . file devkb/packs.py
```

**Expected:** `pack_file` lists the tests; `run` still works.

**Scope:** `devkb/packs.py`, `tests/test_packs.py`.

**Where to start:** `Packer.pack_file` in `devkb/packs.py` (L120-160) and `_tests_for`; then `run`.

**Done when:** the suite is green.
"""


def test_location_names_are_files_and_code_like_names_only():
    names = pb.location_names(BODY)
    assert {"devkb/packs.py", "packs.py", "Packer.pack_file", "_tests_for"} <= set(names)
    assert "run" not in names and "devkb" not in names           # plain words and command names stay


def test_without_location_masks_every_name_in_title_and_body_and_drops_the_section():
    title, body = pb.without_location("Fix `_tests_for` in packs.py", BODY)
    assert "_tests_for" not in title and "packs.py" not in title
    for n in ("devkb/packs.py", "Packer.pack_file", "_tests_for", "L120-160"):
        assert n not in body, n
    assert "**Where to start:** (withheld for this benchmark run)" in body
    assert "tests/test_packs.py" not in body                       # a file named only in Scope is withheld too
    assert "**Expected:**" in body and "`run` still works" in body and "**Done when:**" in body


def test_the_prompt_as_filed_is_unchanged(tmp_path):
    p = pb.prompt_for("999", "T", BODY, tmp_path, hide=False)
    assert "Packer.pack_file" in p and "L120-160" in p
    assert "Packer.pack_file" not in pb.prompt_for("999", "T", BODY, tmp_path, hide=True)


def test_hidden_arms_map_to_their_base_arms():
    assert pb.HIDE_LOCATION == {"nonehid": "none", "mainhid": "main", "rmainhid": "rmain", "routerhid": "router", "ctxhid": "ctx", "bothhid": "both", "bothuserhid": "bothuser"}


def test_the_release_table_compares_like_with_like():
    assert rt.location_given("main") and rt.location_given("none") and not rt.location_given("mainhid")
    assert "nonehid" in rt.NONE and rt.ORDER.index("nonehid") < rt.ORDER.index("mainhid")


def test_a_name_is_withheld_with_whatever_qualifies_it_and_its_line_numbers():
    body = ("**Who is affected:** `Packer._resolve` and `bench/policy/packs.py:120` (L88).\n\n"
            "**Where to start:** `_resolve` in `packs.py`.\n\n**Done when:** green.\n")
    _t, b = pb.without_location("t", body)
    assert "_resolve" not in b and "packs.py" not in b and ":120" not in b and "L88" not in b


def test_scope_files_are_withheld_everywhere_and_version_tags_and_plain_words_are_kept():
    body = ("**Reproduce:** `git checkout v0.2.11 && devkb build` then read `devkb/build_symbols.py:1471`, e.g. the log.\n\n"
            "**Scope:** `devkb/build_symbols.py`.\n\n**Where to start:** `foo_bar`.\n")
    _t, b = pb.without_location("t", body)
    assert "build_symbols" not in b and ":1471" not in b
    assert "v0.2.11" in b and "e.g." in b and "devkb build" in b


def test_a_heading_where_to_start_and_bold_inside_a_fence():
    body = "## Where to start\n\n`foo_bar` in `devkb/x.py`.\n\n## Done when\n\n```\n**Complete.**\nfoo_bar\n```\n"
    assert "foo_bar" in pb.location_names(body) and "devkb/x.py" in pb.location_names(body)
    _t, b = pb.without_location("t", body)
    assert "foo_bar" not in b and "(withheld for this benchmark run)" in b


def test_the_hide_option_maps_run_and_score_alike_and_refuses_an_arm_without_a_hidden_form(monkeypatch):
    import pytest
    monkeypatch.delenv("POLICY_HIDE_START", raising=False)
    assert pb.arms_for(["none", "main"]) == ["none", "main"]
    monkeypatch.setenv("POLICY_HIDE_START", "1")
    assert pb.arms_for(["none", "main"]) == ["nonehid", "mainhid"]
    with pytest.raises(SystemExit, match="nonekeep"):
        pb.arms_for(["nonekeep", "main"])
    assert pb.split_arm("mainhid") == ("main", True) and pb.split_arm("main") == ("main", False)


def test_each_arm_is_compared_with_the_no_devkb_arm_given_the_ticket_the_same_way():
    sums = {"none": "N", "main": "M", "nonehid": "NH", "mainhid": "MH"}
    arms = ["none", "main", "nonehid", "mainhid"]
    assert rt.base_for("mainhid", arms, sums) == "NH" and rt.base_for("main", arms, sums) == "N"
    assert rt.base_for("mainhid", ["none", "mainhid"], sums) is None     # never the location-given control


def test_a_run_gets_the_prompt_of_its_arm(monkeypatch, tmp_path):
    """The wiring `_run_one` uses: a hidden arm's run gets the withheld ticket, its base arm's run the filed one."""
    monkeypatch.setattr(pb, "ticket_for", lambda issue: {"title": "T", "body": BODY})
    assert "Packer.pack_file" not in pb.run_prompt("999", "mainhid", tmp_path)
    assert "Packer.pack_file" in pb.run_prompt("999", "main", tmp_path)
    assert "run_prompt(issue, tag.split" in Path(pb.__file__).read_text()      # and _run_one builds its prompt through it


def test_score_with_the_option_scores_the_hidden_runs(monkeypatch, tmp_path):
    import hashlib
    import json
    (tmp_path / "accept").mkdir()
    (tmp_path / "accept" / "999.py").write_text("print('{}')\n")
    sha = hashlib.sha256((tmp_path / "accept" / "999.py").read_bytes()).hexdigest()
    for arm in ("none", "nonehid"):
        d = tmp_path / "runs" / f"p999-{arm}-r1"
        d.mkdir(parents=True)
        (d / "end").write_text(json.dumps({"exit": 0}))
        (d / "score.json").write_text(json.dumps({"run": d.name, "issue": "999", "arm": arm, "accept_sha256": sha,
                                                  "acceptance": {"pass": True}, "suite_pass": True, "cost": 0.1,
                                                  "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": []}))
    monkeypatch.setattr(pb, "B", tmp_path)
    monkeypatch.setenv("POLICY_HIDE_START", "1")
    monkeypatch.setenv("POLICY_ARMS", "none")
    pb.score(["999"])
    rows = [json.loads(l) for l in (tmp_path / "results-999.jsonl").read_text().splitlines()]
    assert [r["arm"] for r in rows] == ["nonehid"]


def test_symptoms_and_corpus_line_numbers_stay():
    body = ("**Reproduce:** `CLAUDE_PLUGIN_ROOT=/x/plugin devkb` raises `KeyError`; fmt's format.h L1364 shows it.\n\n"
            "**Where to start:** catch (`KeyError`, `TypeError`) in `handle_plan` (`ops/triage/triage.py`); "
            "`CLAUDE_PLUGIN_ROOT` handling.\n\n**Done when:** L1364 is listed.\n")
    names = pb.location_names(body)
    assert "handle_plan" in names and "KeyError" not in names and "CLAUDE_PLUGIN_ROOT" not in names
    _t, b = pb.without_location("t", body)
    assert "KeyError" in b and "CLAUDE_PLUGIN_ROOT=" in b and "L1364 is listed" in b and "format.h L1364" in b


def test_scope_code_names_are_withheld_and_a_name_outside_the_own_code_stays(tmp_path):
    import subprocess
    (tmp_path / "devkb").mkdir()
    (tmp_path / "devkb" / "service.py").write_text("class Staleness:\n    pass\n\ndef _hook():\n    return 1\n")
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "fmt.h").write_text("int count_digits(int n);\n")
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(tmp_path), *c], check=True, capture_output=True)
    body = ("**Actual:** the label reads `in count_digits` and `Staleness` is wrong.\n\n"
            "**Scope:** the message in `devkb/service.py` (`Staleness`).\n\n"
            "**Where to start:** `_hook`; check whether the `count_digits` span is too long.\n")
    _t, b = pb.without_location("t", body, tmp_path)
    assert "Staleness" not in b and "_hook" not in b and "service.py" not in b
    assert "count_digits" in b                      # a corpus function in the symptom: not the place to fix
    assert pb.in_own_code(tmp_path, "Staleness.message") and not pb.in_own_code(tmp_path, "count_digits")


def test_a_broken_repository_withholds_rather_than_leaks(tmp_path):
    (tmp_path / ".git").mkdir()                     # not a valid repository: git grep exits 128
    assert pb.in_own_code(tmp_path, "_resolve")
