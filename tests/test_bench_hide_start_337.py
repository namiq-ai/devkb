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
