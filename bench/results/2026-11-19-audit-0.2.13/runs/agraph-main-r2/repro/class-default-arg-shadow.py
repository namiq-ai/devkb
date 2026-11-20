import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({
    "a.py": "TIMEOUT = 30\n\nclass Client:\n    TIMEOUT = 5\n\n    def run(self, t=TIMEOUT):\n        return t\n\ndef real():\n    return TIMEOUT\n",
    "test_a.py": "from a import Client\ndef test_run():\n    Client().run()\n",
})
rc, out = devkb(d, "pack", "change", "a.py::TIMEOUT")
print(out)
if "Client.run" in out or "a.py:6" in out:
    print("DEFECT: `def run(self, t=TIMEOUT)` inside a class that assigns TIMEOUT reads the class attribute,")
    print("        but the pack attributes it to the module constant (class-body shadowing, #199, misses default values)")
    print("EXPECTED: only `real` (a.py:10) reaches the module constant; test_a.py is not listed")
    sys.exit(1)
print("ok")
