import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({
    "lib.h": "int add(int a, int b);\n",
    "lib.cc": '#include "lib.h"\nint add(int a, int b) { return a + b; }\n',
    "lib_test.cc": '#include "lib.h"\nTEST(Lib, Add) { add(1, 2); }\n',
})
rc, out = devkb(d, "pack", "change", "add")
print(out)
if "lib_test.cc" in out and "Run: ``" in out:
    print("DEFECT: the pack lists a C++ test to run and then prints an empty command: Run: ``")
    print("EXPECTED: a runnable command for the test (or no Run line, or a line saying it cannot name one)")
    sys.exit(1)
print("ok")
