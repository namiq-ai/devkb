"""#86: benchmark scorers strip a leading `./` as a path step, never the characters, so `.github/` keeps its dot."""
from __future__ import annotations

from devkb.bench.run import norm


def test_the_lifecycle_scorer_keeps_a_dot_directory():
    assert norm("./.github/x.py::A.f") == ".github/x.py::f"
    assert norm("`./src/a.py`") == "src/a.py"
    assert norm(".github/x.py") == ".github/x.py"
