"""#371: the C# lambda linearity test does not depend on wall-clock speed. Black box: run the checkout's own test as it
is, and again with every clock the test could read running 20 times slower (a heavily loaded machine); prints one JSON line."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
TEST = "tests/test_csharp_symbols.py::test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method"
SLOW = '''import time
for _n in ("perf_counter", "monotonic", "time", "process_time"):
    _f = getattr(time, _n)
    setattr(time, _n, (lambda f: (lambda: f() * 20))(_f))
for _n in ("perf_counter_ns", "monotonic_ns", "time_ns", "process_time_ns"):
    _f = getattr(time, _n)
    setattr(time, _n, (lambda f: (lambda: f() * 20))(_f))
'''
res = {}
with tempfile.TemporaryDirectory() as td:
    home = Path(td) / "home"
    home.mkdir()
    slow = Path(td) / "slow"
    slow.mkdir()
    (slow / "sitecustomize.py").write_text(SLOW)

    def run(extra=""):
        env = dict(os.environ, HOME=str(home), PYTHONPATH=os.pathsep.join(filter(None, [extra, str(W)])), PYTHONWARNINGS="ignore")
        for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
            env.pop(k, None)
        r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=W, env=env, capture_output=True,
                           text=True, timeout=600)
        return r.returncode == 0 and " passed" in r.stdout

    res["test_exists"] = "def test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method" in (W / "tests/test_csharp_symbols.py").read_text()
    res["passes"] = run()
    res["passes_on_a_20x_slower_clock"] = run(str(slow))
res["pass"] = all(res.values())
print(json.dumps(res))
