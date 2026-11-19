import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
from h import *
d = mk({"m.py": 'import os\ndef a():\n    return os.environ["zz1"]\ndef c():\n    return os.environ.get("zz3")\ndef d():\n    return "zz4" in os.environ\n'})
build(d)
bad = False
for k in ("zz1", "zz3", "zz4"):
    rc, out = dk("uses", "--project", d, k)
    counted = "as a string key" in out
    print(k, "counted as a record string key:", counted)
    bad |= counted
print("expected: os.environ[...] and `in os.environ` are environment reads like os.environ.get, so none is a record-key read (see `uses KEY` config)")
sys.exit(1 if bad else 0)
