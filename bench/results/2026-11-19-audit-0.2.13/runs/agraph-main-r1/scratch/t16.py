import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"m.py": '''
import enum
from typing import NamedTuple
def helper():
    return 1
def tool():
    return 2
def util():
    return 3
class K:
    helper = None
    tool: int = 0
    def run(self):
        return helper()
    def run2(self):
        return self.tool
class N(NamedTuple):
    util: int
class E(enum.Enum):
    helper = 1
def caller():
    return tool() + util()
''',
"n.py": '''
from m import helper, tool
import m
class Z:
    tool = 5
    def zz(self):
        return tool() + m.util()
def w():
    return helper()
''',
"tests/test_m.py": '''
import m, n
def test_a(): assert m.K().run()
def test_b(): assert m.caller()
def test_c(): assert n.Z().zz() and n.w()
''',
}
d = mk(F); build(d)
import re
for nme in ["m.py::helper", "m.py::tool", "m.py::util"]:
    out = dk("pack", "--project", d, "change", nme)[1]
    print(nme, re.findall(r"^- `(.+?)` —", out, re.M), "Complete" if "**Complete" in out else "INCOMPLETE")
