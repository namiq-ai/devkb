import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"core.py": '''
LIMIT = 10
A, (B, C) = 1, (2, 3)
[D, E] = 4, 5
F, *G = 1, 2, 3
H: int = 7
for I in range(3):
    pass
with open("x") as J:
    pass
K = L = 9
''',
"use.py": '''
import core
import core as cc
from core import LIMIT, A
from core import B as BB

def p1():
    return core.LIMIT
def p2():
    return cc.LIMIT
def p3():
    return LIMIT
def p4(LIMIT):
    return LIMIT
def p5():
    LIMIT = 3
    return LIMIT
def p6():
    return [LIMIT for LIMIT in range(3)]
def p7():
    return A
def p8():
    return BB
def p9():
    return core.D + core.E + core.F + core.H + core.K + core.L
def p10():
    lam = lambda LIMIT: LIMIT
    return lam(1)
def p11():
    try:
        pass
    except Exception as LIMIT:
        return LIMIT
def p12():
    import core as LIMIT
    return LIMIT
''',
"tests/test_u.py": '''
import use
def test_p3(): assert use.p3()
def test_p4(): assert use.p4(1)
def test_p5(): assert use.p5()
''',
}
d = mk(F); build(d)
for n in ["LIMIT", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]:
    out = dk("pack", "--project", d, "change", "core.py::" + n)[1]
    import re
    fn = re.findall(r"^- `(.+?)` —", out.split("## Uses")[0].split("## Test")[0], re.M)
    print(n, "funcs:", fn, "| first lines:", out.split("\n")[2][:70], "| cov:", "Complete" in out)
