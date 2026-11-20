import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({"m.py": "import os\n\ndef r(d):\n    return os.environ['HOME_X']\n"})
_fx.build(d)
out, _ = _fx.dk(d, "symbol", "HOME_X", "--project", ".")
print(out)
bad = "string key" in out
print("BAD: os.environ['HOME_X'] is reported as a record string key read" if bad else "ok")
print("expected: not a record key (os.environ.get is already excluded by #202)")
sys.exit(1 if bad else 0)
