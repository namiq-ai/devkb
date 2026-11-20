"""#371: the C# lambda linearity test does not depend on wall-clock speed, and still fails on the quadratic code it guards.
Black box: the checkout's own test, run three ways; prints one JSON line.
- passes: as it is;
- passes_without_wall_clocks: with every wall clock (perf_counter, monotonic, time and their _ns forms) raising when read
  from the test file, so the test cannot depend on how fast the machine is at the moment (other processes' load); CPU time
  (process_time) and work counts stay available. Revised after review of PR #376: a constant 20x clock cannot fail a ratio
  of two wall-clock timings, and such a ratio still failed under uneven load (4 of 30);
- fails_on_the_quadratic_code: with devkb/csharp_symbols.py from 9527a9d^ (before #61's fix) in a copy of the checkout."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
TEST = "tests/test_csharp_symbols.py::test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method"
GUARDED = "9527a9d"
UNEVEN = '''import sys, time
def _wrap(f):
    def g():
        fr = sys._getframe(1)
        while fr is not None:                    # the test (or a helper it defines) reading a wall clock
            if fr.f_code.co_filename.endswith("test_csharp_symbols.py"):
                raise RuntimeError("#371 hidden check: the test read a wall clock")
            fr = fr.f_back
        return f()
    return g
for _n in ("perf_counter", "monotonic", "time", "perf_counter_ns", "monotonic_ns", "time_ns"):
    setattr(time, _n, _wrap(getattr(time, _n)))
'''
res = {}
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    home = td / "home"
    home.mkdir()
    (td / "uneven").mkdir()
    (td / "uneven" / "sitecustomize.py").write_text(UNEVEN)

    def run(root, extra=""):
        env = dict(os.environ, HOME=str(home), PYTHONPATH=os.pathsep.join(filter(None, [extra, str(root)])), PYTHONWARNINGS="ignore")
        for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
            env.pop(k, None)
        r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=root, env=env, capture_output=True,
                           text=True, timeout=900)
        return r.returncode == 0 and " passed" in r.stdout

    res["test_exists"] = "def test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method" in (W / "tests/test_csharp_symbols.py").read_text()
    res["passes"] = run(W)
    res["passes_without_wall_clocks"] = run(W, str(td / "uneven"))
    for repo in (W, Path(__file__).resolve().parents[3]):   # the checkout's history, else the harness repository's
        old = subprocess.run(["git", "-C", str(repo), "show", f"{GUARDED}^:devkb/csharp_symbols.py"], capture_output=True, text=True)
        if old.returncode == 0:
            break
    if old.returncode == 0:
        cp = td / "copy"
        shutil.copytree(W, cp, ignore=shutil.ignore_patterns(".git", ".venv", ".devkb", "corpus", "__pycache__"))
        (cp / "devkb" / "csharp_symbols.py").write_text(old.stdout)
        res["fails_on_the_quadratic_code"] = not run(cp)
    else:
        res["fails_on_the_quadratic_code"] = False
res["pass"] = all(res.values())
print(json.dumps(res))
