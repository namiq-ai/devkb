"""#309: quoted text and comments are not commands; only reads inside the listed folder count."""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "audit"))
sys.path.insert(0, str(HERE / "bench" / "exploration"))
toolmix = importlib.import_module("toolmix")
ltr = importlib.import_module("listing_then_read")


def test_a_commit_message_that_mentions_devkb_is_not_a_devkb_query():
    c = 'git commit -m "docs: explain devkb symbol output"'
    assert toolmix.devkb_queries(c) == 0 and toolmix.classify("Bash", {"command": c}) == "other"


def test_a_trailing_comment_is_not_a_command():
    c = 'grep -rn --include=*.md -e "text" docs # see devkb uses'
    assert toolmix.devkb_queries(c) == 0 and toolmix.classify("Bash", {"command": c}) == "search"


def test_real_devkb_queries_still_count():
    for c in ("devkb symbol parse", "cd x && .venv/bin/devkb pack --project . file a.py", "python -m devkb.cli uses foo",
              'bash -c "devkb symbol parse"', "echo hi; devkb outline a.py # note"):
        assert toolmix.devkb_queries(c) == 1, c
    assert toolmix.devkb_queries('P="python -m devkb.cli"; $P uses X') == 1


def test_a_read_after_a_bare_ls_must_be_inside_the_working_directory():
    assert ltr.inside(".", "src/a.py") and ltr.inside("", "a.py")
    assert not ltr.inside(".", "/etc/hosts") and not ltr.inside(".", "../other/a.py")
    assert ltr.inside("src", "src/a.py") and not ltr.inside("src", "other/a.py")
