"""#287: a module constant's reads are attributed exactly: a lambda parameter, `except ... as`, `case` capture or a class-body
default that shadows it is not a read, and `pkg.sub.mod.NAME` (after `import pkg.sub.mod`) is one."""
from test_constant_reads_198_199_200 import cli, repo


def test_lambda_except_and_match_bindings_are_not_reads(tmp_path):
    src = ("LIMIT = 10\n\n\ndef real():\n    return LIMIT\n\n\ndef p_lambda():\n    f = lambda LIMIT: LIMIT\n    return f(1)\n\n\n"
           "def p_except():\n    try:\n        pass\n    except Exception as LIMIT:\n        return LIMIT\n\n\n"
           "def p_match():\n    match [1, 2]:\n        case [LIMIT, *REST]:\n            return LIMIT\n\n\n"
           "def p_lambda_default(x=LIMIT):\n    return (lambda y=LIMIT: y)\n")
    out = cli(repo(tmp_path, {"m.py": src}), "pack", "change", "m.py::LIMIT")
    assert "`m.py:5`" in out                                   # precision: the real read stays
    assert "`m.py:26`" in out and "`m.py:27`" in out                                # a lambda default is read in the enclosing scope
    for line in (9, 17, 22, 23):
        assert f"`m.py:{line}`" not in out, line


def test_class_body_default_is_not_a_read_of_the_module_constant(tmp_path):
    src = ("TIMEOUT = 30\n\n\nclass Client:\n    TIMEOUT = 5\n\n    def run(self, t=TIMEOUT):\n        return t\n\n\n"
           "def real():\n    return TIMEOUT\n\n\nclass Other:\n    def run(self, t=TIMEOUT):\n        return t\n")
    out = cli(repo(tmp_path, {"a.py": src}), "pack", "change", "a.py::TIMEOUT")
    assert "`a.py:12`" in out and "`a.py:16`" in out and "`a.py:7`" not in out


def test_dotted_module_path_read_is_attributed(tmp_path):
    r = repo(tmp_path, {"pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/impl.py": "CONST = 4\n",
                        "use.py": "import pkg.sub.impl\n\n\ndef f():\n    return pkg.sub.impl.CONST\n",
                        "other.py": "import pkg\n\n\ndef g(obj):\n    return obj.sub.impl.CONST\n"})
    out = cli(r, "pack", "change", "pkg/sub/impl.py::CONST")
    assert "`use.py:5`" in out and "`other.py:5`" not in out
