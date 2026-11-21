"""#305: a setup error is recorded as an error and retried; a run refused for a red base is set up again in the next
batch; a finished run is still skipped. Black box on policybench._run_one with the setup stubbed."""
import importlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")

calls = []


def stub(exc):
    def f(*a, **k):
        calls.append(1)
        raise exc
    return f


def attempt(td, end, exc):
    """Run the one run in a fresh B holding `end` as its end file; return (setup attempted, the end file afterwards)."""
    pb.B = Path(td)
    out = Path(td) / "runs" / "p9-none-r1"
    out.mkdir(parents=True)
    if end is not None:
        (out / "end").write_text(json.dumps(end))
    calls.clear()
    pb.template_for = lambda arm, issue=None: "x"
    pb.from_template = stub(exc)
    pb.checkout = stub(exc)
    try:
        pb._run_one("9", "none", 1)
    except Exception:  # noqa: BLE001  anything after the setup is out of scope here
        pass
    return bool(calls), json.loads((out / "end").read_text()) if (out / "end").exists() else None


res = {}
with tempfile.TemporaryDirectory() as td:
    tried, end = attempt(td, {"exit": "base-red", "seconds": 0, "error": "red"}, RuntimeError("base is red"))
    res["base_red_is_retried"] = tried
with tempfile.TemporaryDirectory() as td:
    tried, end = attempt(td, None, OSError("uv pip install: connection reset"))
    res["setup_error_is_recorded_as_error_not_base_red"] = bool(end) and end.get("exit") == "error"
with tempfile.TemporaryDirectory() as td:
    tried, end = attempt(td, {"exit": "error", "seconds": 0, "error": "setup: OSError"}, OSError("connection reset"))
    res["recorded_setup_error_is_retried"] = tried
with tempfile.TemporaryDirectory() as td:
    tried, end = attempt(td, {"exit": 0, "seconds": 5}, RuntimeError("must not be reached"))
    res["finished_run_is_skipped"] = not tried
with tempfile.TemporaryDirectory() as td:
    tried, end = attempt(td, None, RuntimeError("base is red"))
    res["a_red_base_is_still_recorded"] = bool(end) and end.get("exit") == "base-red"
res["pass"] = all(res.values())
print(json.dumps(res))
