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
    assert pb.HIDE_LOCATION == {"nonehid": "none", "mainhid": "main"}


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
