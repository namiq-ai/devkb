"""#372: `devkb symbol NAME` lists the match spelled as the query first, and marks matches in another case as such;
case alone still never lifts test code above production code.
Black box: the checkout's own CLI on fixture repositories; prints one JSON line."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
res = {}
with tempfile.TemporaryDirectory() as td:
    home = Path(td) / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)

    def run(d, *a):
        return subprocess.run([py, "-P", "-m", "devkb.cli", *a], cwd=d, env=env, capture_output=True, text=True, timeout=300).stdout

    def mk(name, files):
        d = Path(td) / name
        for rel, txt in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(txt)
        for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
            subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)
        run(d, "build", "--project", str(d))
        return d

    def entries(out):
        """[(file, name line, how line)] for each numbered match."""
        lines = out.splitlines()
        got = []
        for i, l in enumerate(lines):
            m = re.match(r"\s*\d+\.\s+(\S+)\s", l)
            if m:
                got.append((m.group(1), l, lines[i + 1] if i + 1 < len(lines) else ""))
        return got

    # production: a lowercase function with callers, and the constant spelled as the query, with none
    d = mk("case", {
        "pkg/tools.py": "def trace(text):\n    return text\n\ndef use():\n    return trace('x')\n\ndef use2():\n    return trace('y')\n",
        "pkg/settings.py": "TRACE = ('a', 'b')\n",
    })
    out = run(d, "symbol", "TRACE", "--project", str(d))
    e = entries(out)
    res["two_matches"] = len(e) == 2
    res["exact_case_first"] = bool(e) and e[0][0] == "pkg/settings.py"
    other = [x for x in e if x[0] == "pkg/tools.py"]
    res["other_case_marked"] = bool(other) and "case" in other[0][2].lower()
    exact = [x for x in e if x[0] == "pkg/settings.py"]
    res["exact_case_not_marked"] = bool(exact) and "case" not in exact[0][2].lower()
    # the query in lowercase: the function is the exact spelling now
    e = entries(run(d, "symbol", "trace", "--project", str(d)))
    res["lowercase_query_function_first"] = bool(e) and e[0][0] == "pkg/tools.py"

    # case never lifts a test symbol above production code
    d = mk("tests", {
        "app/core.py": "def parse(s):\n    return s\n",
        "tests/test_core.py": "def Parse():\n    return 1\n\ndef test_it():\n    assert Parse() == 1\n",
    })
    e = entries(run(d, "symbol", "Parse", "--project", str(d)))
    res["production_before_exact_case_test"] = bool(e) and e[0][0] == "app/core.py"

res["pass"] = all(res.values())
print(json.dumps(res))
