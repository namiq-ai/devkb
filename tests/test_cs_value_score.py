"""bench/cs_value.py scoring: hand corrections beside the compiler truth, and no hidden wrong names."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import cs_value  # noqa: E402

Q = {"name": "Target", "truth": ["T.Prop"], "uncertain": [],
     "truth_property_reads": ["Reader"], "uncertain_by_hand": ["Callback"],
     "production_methods": ["Prop", "Reader", "Callback", "Other"] + [f"W{i}" for i in range(15)]}


def test_corrections_count_unless_compiler_only():
    text = "`Prop`, `Reader`, `Callback`, `Other`"
    fixed, plain = cs_value.score(Q, text), cs_value.score(Q, text, compiler_only=True)
    assert (fixed["right"], fixed["wrong"], fixed["wrong_names"]) == (2, 1, ["Other"])
    assert (plain["right"], plain["wrong"]) == (1, 3)
    assert fixed["R"] == 1.0 and plain["R"] == 1.0


def test_every_wrong_name_is_reported():
    text = " ".join(f"`W{i}`" for i in range(15))
    assert len(cs_value.score(Q, text)["wrong_names"]) == 15
