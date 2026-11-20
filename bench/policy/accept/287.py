"""#287: a module constant's reads are attributed exactly. A local binding that shadows it (lambda parameter, `except ... as`, `case` capture,
method default in a class that defines the name) is not a read; a read through a dotted module path is listed, or the pack is not Complete.
Black box: the checkout's own CLI on a fixture repository; prints one JSON line."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/ip/devkb/.venv/bin/python")
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

    # shadowing locals: none of these functions reads the module constant
    shadows = {
        "p_lambda": "    f = lambda LIMIT: LIMIT\n    return f(1)\n",
        "p_except": "    try:\n        pass\n    except Exception as LIMIT:\n        return LIMIT\n",
        "p_match": "    match 1:\n        case LIMIT:\n            return LIMIT\n",
        "p_matchseq": "    match [1, 2]:\n        case [LIMIT, _]:\n            return LIMIT\n",
        "p_with": "    with open('x') as LIMIT:\n        return LIMIT\n",
        "p_for": "    for LIMIT in range(3):\n        return LIMIT\n",
    }
    src = "LIMIT = 10\n\ndef real():\n    return LIMIT\n\ndef p_param(LIMIT=3):\n    return LIMIT\n\n" + "".join(f"def {k}():\n{v}\n" for k, v in shadows.items())
    shadows["p_param"] = ""
    d = mk("shadow", {"m.py": src})
    out = run(d, "pack", "--project", str(d), "change", "m.py::LIMIT")
    res["shadow_real_read_listed"] = "m.py::real" in out
    for k in shadows:
        res[f"shadow_{k}_not_listed"] = f"m.py::{k}`" not in out and f"m.py::{k} " not in out and f"m.py::{k}\n" not in out

    # class-level default shadowing
    d = mk("clsdef", {
        "a.py": "TIMEOUT = 30\n\nclass Client:\n    TIMEOUT = 5\n\n    def run(self, t=TIMEOUT):\n        return t\n\ndef real():\n    return TIMEOUT\n",
        "test_a.py": "from a import Client\ndef test_run():\n    Client().run()\n"})
    out = run(d, "pack", "--project", str(d), "change", "a.py::TIMEOUT")
    res["classdefault_real_listed"] = "a.py::real" in out
    res["classdefault_method_not_listed"] = "Client.run" not in out and "a.py:6" not in out

    # dotted reads: each reader listed, or the pack is not Complete
    d = mk("dotted", {
        "pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/impl.py": "CONST = 4\n",
        "use.py": "import pkg.sub.impl\ndef f():\n    return pkg.sub.impl.CONST\n",
        "use2.py": "import pkg.sub.impl as m\ndef g():\n    return m.CONST\n",
        "use3.py": "from pkg.sub import impl\ndef h():\n    return impl.CONST\n",
        "tests/test_u.py": "import use, use2, use3\ndef test_a():\n    use.f(); use2.g(); use3.h()\n"})
    out = run(d, "pack", "--project", str(d), "change", "CONST")
    complete = "**Complete" in out
    for f in ("use.py::f", "use2.py::g", "use3.py::h"):
        res[f"dotted_{f.split('::')[1]}_listed_or_incomplete"] = (f in out) or not complete

    # regression guard: a direct import of the constant stays attributed
    d = mk("direct", {"c.py": "K = 1\n", "u.py": "from c import K\ndef r():\n    return K\n"})
    out = run(d, "pack", "--project", str(d), "change", "c.py::K")
    res["direct_import_read_listed"] = "u.py::r" in out
res["pass"] = all(res.values())
print(json.dumps(res))
