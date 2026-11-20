import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {"m.py": '''
import os
def a():
    return os.environ["zz1"]
def b():
    return os.getenv("zz2")
def c():
    return os.environ.get("zz3")
def d():
    return "zz4" in os.environ
def e(self):
    return self.cfg["zz5"], self.cfg.get("zz6")
'''}
d = mk(F); build(d)
for k in ["zz1", "zz2", "zz3", "zz4", "zz5", "zz6"]:
    print(k, dk("uses", "--project", d, k)[1][:300].replace("\n", " | "))
