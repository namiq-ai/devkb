"""#195: extracting module constants is linear (0.2.12 scanned every symbol of the file per constant), and a name
assigned twice is still one symbol."""
from pathlib import Path

import work_counter

from devkb import build_symbols


def _work(path: Path) -> int:
    """Lines of build_symbols.py executed while one file is parsed: the same on every run, unlike seconds (#377)."""
    return work_counter.lines_executed(lambda: build_symbols._parse_python_file(path, []), build_symbols.__file__)[0]


def test_three_times_the_constants_take_about_three_times_the_work(tmp_path):
    small, large = tmp_path / "s.py", tmp_path / "l.py"
    small.write_text("\n".join(f"NAME_{i} = {i}" for i in range(2000)) + "\n")
    large.write_text("\n".join(f"NAME_{i} = {i}" for i in range(6000)) + "\n")
    ratio = _work(large) / _work(small)
    assert ratio < 4.5, ratio                     # linear is 3.0 exactly; a scan of every symbol of the file per constant gives about 9


def test_a_name_assigned_twice_and_a_repeated_field_are_one_symbol_each(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("from dataclasses import dataclass\n\nX = 1\nX = 2\n\n\ndef X2():\n    pass\n\n\n@dataclass\nclass P:\n    port: int = 0\n    port: int = 1\n")
    names = [s["qualified_name"] for s in build_symbols._parse_python_file(f, [])[0]]
    assert names.count("X") == 1 and names.count("P.port") == 1 and "X2" in names and "P" in names
