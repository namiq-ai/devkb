import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"pkg/__init__.py": "from .core import LIMIT\n",
"pkg/core.py": "LIMIT = 10\nOTHER = 1\n",
"star.py": "from pkg.core import *\ndef s1():\n    return LIMIT\n",
"reexp.py": "import pkg\nfrom pkg import LIMIT as L2\ndef r1():\n    return pkg.LIMIT\ndef r2():\n    return L2\n",
"misc.py": '''
from pkg.core import LIMIT
def d1(x=LIMIT):
    return x
def d2():
    return f"{LIMIT}"
def d3():
    def inner():
        return LIMIT
    return inner
class Q:
    def m(self):
        self.v = LIMIT
    @property
    def p(self):
        return LIMIT
@some_decorator(LIMIT)
def d4():
    pass
def d5():
    return {LIMIT: 1}
def d6(a: "int" = LIMIT):
    pass
async def d7():
    return LIMIT
def d8():
    return [LIMIT]
x = LIMIT
''',
"tests/test_m.py": '''
import misc, star, reexp
def test_all():
    misc.d1(); misc.d2(); star.s1(); reexp.r1(); reexp.r2()
''',
}
d = mk(F); build(d)
out = dk("pack", "--project", d, "change", "pkg/core.py::LIMIT")[1]
print(out)
