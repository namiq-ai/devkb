"""#195: extracting module constants is linear (0.2.12 scanned every symbol of the file per constant), and a name
assigned twice is still one symbol."""
import time
from pathlib import Path

from devkb import build_symbols


def _secs(path: Path) -> float:
    t = time.perf_counter()
    build_symbols._parse_python_file(path, [])
    return time.perf_counter() - t


def test_three_times_the_constants_take_about_three_times_as_long(tmp_path):
    small, large = tmp_path / "s.py", tmp_path / "l.py"
    small.write_text("\n".join(f"NAME_{i} = {i}" for i in range(6000)) + "\n")
    large.write_text("\n".join(f"NAME_{i} = {i}" for i in range(18000)) + "\n")
    _secs(small)
    # best of three for each size, so a busy machine (the benchmark runs agents in parallel) does not flake it
    ratio = min(_secs(large) for _ in range(3)) / min(_secs(small) for _ in range(3))
    assert ratio < 5.5, ratio                     # linear is about 3; 0.2.12 gave 7 at these sizes


def test_a_name_assigned_twice_and_a_repeated_field_are_one_symbol_each(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("from dataclasses import dataclass\n\nX = 1\nX = 2\n\n\ndef X2():\n    pass\n\n\n@dataclass\nclass P:\n    port: int = 0\n    port: int = 1\n")
    names = [s["qualified_name"] for s in build_symbols._parse_python_file(f, [])[0]]
    assert names.count("X") == 1 and names.count("P.port") == 1 and "X2" in names and "P" in names
