"""A transient setup failure (uv/network, disk) is recorded as exit "base-red" and the run is skipped on every later batch."""
import json, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "bench" / "policy"))
import policybench as pb  # noqa: E402

pb.B = Path(tempfile.mkdtemp())
calls = []


def flaky_setup(arm):
    calls.append(arm)
    if len(calls) == 1:
        raise OSError("uv pip install: connection reset")     # transient
    raise StopIteration                                       # stands for "setup worked, the run went on"


pb.template_for = flaky_setup
first = pb._run_one("205", "main", 1)
end = json.loads((pb.B / "runs" / "p205-main-r1" / "end").read_text())
print("first batch:", first, "| end file:", end["exit"])
try:
    second = pb._run_one("205", "main", 1)
except StopIteration:
    second = "setup was attempted again"
print("second batch:", second, "| setup attempts:", len(calls))
print("expected: the second batch tries the setup again; a setup error is not a red base")
sys.exit(1 if len(calls) < 2 or end["exit"] == "base-red" else 0)
