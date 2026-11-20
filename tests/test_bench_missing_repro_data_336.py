"""#336: a reproduction block whose data is not in the checkout is replaced by one line saying so; everything else stays as filed."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")

GONE = "bench/results/2026-11-19-audit-0.2.13/runs/aops-main-r1"
BODY = ("**Reproduce:**\n```\nrm -rf audit && cp -r " + GONE + " audit && PYTHONPATH=audit .venv/bin/python audit/repro/x.py\n```\n"
        "**Expected:**\n- the fix\n```\n$ ls src\n```\n")


def test_a_block_with_missing_data_becomes_one_line_and_the_rest_stays(tmp_path):
    out = pb.without_missing_data(BODY, tmp_path)
    assert GONE in out and "is not in this checkout" in out               # named once, in the note
    assert "rm -rf audit" not in out and "PYTHONPATH" not in out
    assert "**Expected:**\n- the fix\n```\n$ ls src\n```\n" in out        # a block that names nothing missing is kept verbatim
    assert out.startswith("**Reproduce:**\n")


def test_a_block_whose_data_exists_is_kept(tmp_path):
    (tmp_path / GONE).mkdir(parents=True)
    assert pb.without_missing_data(BODY, tmp_path) == BODY


def test_a_ticket_without_such_a_path_is_unchanged(tmp_path):
    plain = "Title\n```\npytest -q\n```\ntext bench/results/2026-11-19-audit-0.2.13/ outside a block stays\n"
    assert pb.without_missing_data(plain, tmp_path) == plain
