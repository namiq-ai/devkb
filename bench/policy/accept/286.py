"""#286: a call through a star re-export (`from .sub import *`) is attributed to its target, or the pack is not Complete. Black box: the
checkout's own CLI on small fixture repositories; each case passes if the callers (and the test) are listed, or Coverage is not Complete."""
import json, os, re, subprocess, sys, tempfile
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

    def case(name, files, kind, subject, callers, test_file):
        d = Path(td) / name
        for rel, txt in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(txt)
        for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
            subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)

        def run(*a):
            return subprocess.run([py, "-P", "-m", "devkb.cli", *a], cwd=d, env=env, capture_output=True, text=True, timeout=300).stdout

        run("build", "--project", str(d))
        out = run("pack", "--project", str(d), kind, subject)
        listed = all(c in out for c in callers) and test_file in out
        complete = "**Complete" in out
        if kind == "refactor":      # `pack refactor` has no test-to-run section; the test files it lists are judged by parity (below)
            res[name] = all(c in out for c in callers) or not complete
        else:
            res[name] = listed or not complete
        return out

    star = "from .sub import *\n"
    case("star_with_all_pack_change",
         {"pkg/__init__.py": star, "pkg/sub.py": "__all__ = ['subfn']\ndef subfn():\n    return 1\n",
          "app.py": "import pkg\nfrom pkg import subfn\ndef direct():\n    return subfn()\ndef via_pkg():\n    return pkg.subfn()\n",
          "tests/test_app.py": "import app\ndef test_direct():\n    app.direct()\ndef test_via():\n    app.via_pkg()\n"},
         "change", "pkg/sub.py::subfn", ["app.py::direct", "app.py::via_pkg"], "tests/test_app.py")
    star_out = case("star_with_all_pack_refactor",
         {"pkg/__init__.py": star, "pkg/sub.py": "__all__ = ['starfn']\n\ndef starfn():\n    return 3\n",
          "pkg/user.py": "import pkg\nfrom pkg import starfn\n\ndef c():\n    return starfn()\n\ndef g():\n    return pkg.starfn()\n",
          "tests/test_u.py": "from pkg import user\n\ndef test_c():\n    user.c()\n"},
         "refactor", "starfn", ["user.py"], "tests/test_u.py")
    case("star_without_all",
         {"pkg/__init__.py": star, "pkg/sub.py": "def a_fn():\n    return 1\n",
          "use.py": "from pkg import a_fn\n\ndef a():\n    return a_fn()\n",
          "tests/test_u.py": "import use\n\ndef test_a():\n    use.a()\n"},
         "change", "pkg/sub.py::a_fn", ["use.py::a"], "tests/test_u.py")
    named_out = case("named_reexport_refactor_guard",
         {"pkg/__init__.py": "from .sub import starfn\n", "pkg/sub.py": "__all__ = ['starfn']\n\ndef starfn():\n    return 3\n",
          "pkg/user.py": "import pkg\nfrom pkg import starfn\n\ndef c():\n    return starfn()\n\ndef g():\n    return pkg.starfn()\n",
          "tests/test_u.py": "from pkg import user\n\ndef test_c():\n    user.c()\n"},
         "refactor", "starfn", ["user.py"], "tests/test_u.py")
    tests_of = lambda o: sorted(set(re.findall(r"tests/[\w./-]+\.py", o)))
    # parity: the star case lists exactly the test files the named re-export case lists (or is not Complete)
    res["star_refactor_tests_match_named"] = tests_of(star_out) == tests_of(named_out) or "**Complete" not in star_out
    # regression guard: the named re-export (#192) stays attributed
    case("named_reexport_guard",
         {"pkg/__init__.py": "from .sub import namedfn\n", "pkg/sub.py": "def namedfn():\n    return 1\n",
          "use.py": "from pkg import namedfn\n\ndef a():\n    return namedfn()\n",
          "tests/test_u.py": "import use\n\ndef test_a():\n    use.a()\n"},
         "change", "pkg/sub.py::namedfn", ["use.py::a"], "tests/test_u.py")
res["pass"] = all(res.values())
print(json.dumps(res))
