"""#393: a search piped into a bare `head` or `tail` is a cut at their default of 10 lines, and its answer reaches the agent."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import devkb_guardrail as g  # noqa: E402
import test_devkb_guardrail_cut_search_281 as t281  # noqa: E402

repo = t281.repo        # the same built repository


@pytest.mark.parametrize("cmd, n", [("grep -rn devkb_nav bench | head", 10), ("grep -rn devkb_nav bench | tail", 10),
                                    ("grep -rn x . | head -5", 5), ("grep -rn x . | tail -n +3", None), ("grep -rn x .", None),
                                    ("grep -rn x . | head | head -3", 3)])
def test_a_bare_head_or_tail_is_a_cut_of_ten_lines(cmd, n):
    assert g.output_limit("Bash", {"command": cmd}) == n


def test_the_answer_to_a_search_piped_into_a_bare_head_is_delivered(repo, tmp_path):
    h = t281.hook(repo, tmp_path, "Bash", {"command": "grep -rn helper pkg | head"})
    assert t281.rows(h) >= 1, h        # before the fix the answer was built and logged, then lost to the crash
    assert t281.rows(h) <= 10


@pytest.mark.parametrize("cmd, n", [("grep -rn x . | head -n +5", 5), ("grep -rn x . | head --lines=+3", 3), ("grep -rn x . | tail -n +5", None)])
def test_a_plus_count_is_a_skip_for_tail_and_a_cap_for_head(cmd, n):      # found by the two-way review of #408
    assert g.output_limit("Bash", {"command": cmd}) == n
