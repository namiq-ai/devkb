"""#382: a test that binds a module to a short alias (`sb = importlib.import_module("storybench")`, or a module loaded
with `spec_from_file_location`) is among that module's tests to run; a load the graph cannot follow is not reported
as "no tests".
Black box: the checkout's own CLI, on fixture repositories and on the checkout itself; prints one JSON line."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
res = {}


def tests_listed(out):
    """Test files named in the pack's 'Tests that exercise it' section, and that section's text."""
    m = re.search(r"## Tests that exercise it.*?(?=\n## |\Z)", out, re.S)
    sec = m.group(0) if m else ""
    return set(re.findall(r"^- `([^`]+)`", sec, re.M)), sec


with tempfile.TemporaryDirectory() as td:
    home = Path(td) / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)

    def run(d, *a):
        return subprocess.run([py, "-P", "-m", "devkb.cli", *a], cwd=d, env=env, capture_output=True, text=True,
                              timeout=900).stdout

    def mk(name, files):
        d = Path(td) / name
        for rel, txt in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(txt)
        for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
            subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)
        run(d, "build", "--project", str(d))
        return d

    d = mk("alias", {
        "tools/storyline.py": "def count_turns(rows):\n    return len(rows)\n\n\ndef other():\n    return 0\n",
        "tools/gatekeep.py": "def decide(x):\n    return x > 1\n",
        "other/gatekeep.py": "def decide(x):\n    return x < 1\n",      # the bare name alone cannot tell which
        "tools/dynamo.py": "def spin():\n    return 3\n",
        "tests/test_alias.py": (
            "import importlib\nimport sys\nfrom pathlib import Path\n\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / \"tools\"))\n"
            "sl = importlib.import_module(\"storyline\")\n\n\n"
            "def test_count():\n    assert sl.count_turns([1, 2]) == 2\n"),
        "tests/test_spec.py": (
            "import importlib.util\nfrom pathlib import Path\n\n"
            "HERE = Path(__file__).resolve().parents[1]\nTOOLS = HERE / \"tools\"\n"
            "spec = importlib.util.spec_from_file_location(\"gk_mod\", TOOLS / \"gatekeep.py\")\n"
            "gk = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(gk)\n\n\n"
            "def test_decide():\n    assert gk.decide(2)\n"),
        "tests/test_dyn.py": (
            "import importlib\nimport os\nimport sys\nfrom pathlib import Path\n\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / \"tools\"))\n"
            "dm = importlib.import_module(os.environ.get(\"DYN_MODULE\", \"dyn\" + \"amo\"))\n\n\n"
            "def test_spin():\n    assert dm.spin() == 3\n"),
    })
    got, _ = tests_listed(run(d, "pack", "--project", str(d), "file", "tools/storyline.py"))
    res["aliased_import_module_listed"] = "tests/test_alias.py" in got
    got, _ = tests_listed(run(d, "pack", "--project", str(d), "file", "tools/gatekeep.py"))
    other, _ = tests_listed(run(d, "pack", "--project", str(d), "file", "other/gatekeep.py"))
    _, sec = tests_listed(run(d, "pack", "--project", str(d), "file", "tools/gatekeep.py"))
    line = next((l for l in sec.splitlines() if l.startswith("- `tests/test_spec.py`")), "")
    res["aliased_spec_from_file_location_listed"] = "gk.decide" in line and "tests/test_spec.py" not in other  # by its call
    got, sec = tests_listed(run(d, "pack", "--project", str(d), "file", "tools/dynamo.py"))
    res["unfollowable_load_not_silent"] = "tests/test_dyn.py" in got or bool(
        re.search(r"(?i)incomplete|may be missing|may miss|cannot follow|could not follow", sec))

    # the checkout itself: every test file that binds a bench module to an alias with a literal name is listed
    run(W, "build", "--project", str(W))
    mods = {"storybench": "bench/policy/storybench.py", "policybench": "bench/policy/policybench.py",
            "release_table": "bench/policy/release_table.py", "gate": "bench/review/gate.py"}
    missing = {}
    for mod, path in mods.items():
        want = {f"tests/{p.name}" for p in (W / "tests").glob("test_*.py")
                if re.search(rf"^\s*\w+\s*=\s*importlib\.import_module\(\s*[\"']{mod}[\"']\s*\)", p.read_text(errors="replace"), re.M)}
        got, _ = tests_listed(run(W, "pack", "--project", str(W), "file", path))
        if want - got:
            missing[path] = sorted(want - got)
    res["bench_alias_tests_listed"] = not missing
    got, _ = tests_listed(run(W, "pack", "--project", str(W), "file", "bench/policy/storybench.py"))
    res["case_302_listed"] = "tests/test_bench_run_measures_258.py" in got

print(json.dumps({"results": res, "missing": missing, "pass": all(res.values())}))
