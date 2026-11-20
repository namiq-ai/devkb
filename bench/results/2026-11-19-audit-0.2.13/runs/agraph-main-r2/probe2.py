import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "a.py": '''
import os
_CACHE = None
LIMIT = 3
A, (B, C) = 1, (2, 3)
D = E = 4
F: int = 5
G += 1
class K:
    LIMIT = 2
    y = LIMIT
    def f(self):
        return LIMIT
def get():
    global _CACHE
    if _CACHE is None:
        _CACHE = object()
    return _CACHE
def use_aug():
    global LIMIT
    LIMIT += 1
def use_for():
    for LIMIT in range(3):
        pass
def use_walrus():
    if (LIMIT := 3):
        pass
def use_comp():
    return [LIMIT for LIMIT in range(3)]
def use_with():
    with open("x") as LIMIT:
        pass
def use_except():
    try:
        pass
    except Exception as LIMIT:
        pass
def use_del():
    return B, C, D, E, F
def lam():
    return lambda LIMIT: LIMIT
def nested():
    LIMIT = 1
    def inner():
        return LIMIT
    return inner
def nested2():
    global LIMIT
    def inner():
        return LIMIT
    return inner
def imp():
    from x import LIMIT
    return LIMIT
''',
    "test_a.py": "from a import get, use_del\ndef test_g():\n    get()\ndef test_d():\n    use_del()\n",
}
d, out = build(files)
for q in sys.argv[1:]:
    print("=====", q)
    print(devkb(d, *q.split())[1][:2500])
