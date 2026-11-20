import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
from h import *
d = mk({
    "a.h": "#define DEBUGONLY(x) dbg(x)\n",
    "fa.cc": "void dbg(int){}\nvoid real(int){}\n",
    "c.cc": '#include "a.h"\n#undef DEBUGONLY\nvoid DEBUGONLY(int);\nvoid use3() { DEBUGONLY(2); }\n',
    "e.cc": "void DEBUGONLY(int);\nvoid use5() { DEBUGONLY(2); }\n",
})
build(d)
rc, out = dk("pack", "--project", d, "change", "dbg")
print(out[:700])
bad = "use3" in out or "use5" in out
print("actual: use3 (macro #undef'd, name redeclared as a function) and use5 (header never included, own declaration) are listed as reaching `dbg`" if bad else "ok")
print("expected: neither is linked to the macro's callee")
sys.exit(1 if bad else 0)
