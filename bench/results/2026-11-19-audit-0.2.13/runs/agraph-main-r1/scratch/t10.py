import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {"m.py": '''
import os
def a(d):
    return d["key"]
def b(d):
    d["key"] = 1
def c(d):
    return d.get("key")
def e(d):
    return "key" not in d
def f(d):
    d.pop("key")
def g(d):
    del d["key"]
def h():
    return {"key": 1}
def i(d):
    d.setdefault("key", 2)
def j():
    return os.getenv("key"), os.environ["key"], os.environ.get("key")
def k(d):
    d["key"] -= 1
    d["key"].append(3)
def l(d):
    for x in d["key"]:
        pass
    return dict(key=3)
def key_helper():
    pass
def keyword():
    pass
'''}
d = mk(F); build(d)
print(dk("symbol", "--project", d, "key")[1])
print(dk("uses", "--project", d, "key")[1])
