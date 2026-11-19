import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _h

d = _h.make({
 "pkg/__init__.py": "",
 "pkg/sub/__init__.py": "",
 "pkg/sub/impl.py": "CONST = 4\n",
 "use.py": "import pkg.sub.impl\ndef f():\n    return pkg.sub.impl.CONST\n",
 "use2.py": "import pkg.sub.impl as m\ndef g():\n    return m.CONST\n",
 "use3.py": "from pkg.sub import impl\ndef h():\n    return impl.CONST\n",
 "tests/test_u.py": "import use, use2, use3\ndef test_a():\n    use.f(); use2.g(); use3.h()\n",
})
_h.build(d)
rc, out = _h.dk("pack", "--project", d, "change", "CONST")
print(out.split("---")[0])
missing = [f for f in ("use.py::f", "use2.py::g", "use3.py::h") if f not in out]
complete = "**Complete.**" in out
print("expected: all three readers listed; missing:", missing, "Complete:", complete)
sys.exit(1 if missing and complete else 0)
