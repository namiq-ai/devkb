import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({
    "legacy.h": "#define run(x) legacy_helper(x)\nvoid legacy_helper(int);\n",
    "legacy.cc": '#include "legacy.h"\nvoid legacy_helper(int) {}\nvoid old_user() { run(1); }\n',
    "modern.cc": "// does not include legacy.h and has its own run()\nvoid run(int x) {}\nvoid new_user() { run(2); }\n",
})
rc, out = devkb(d, "pack", "change", "legacy_helper")
print(out)
rc2, out2 = devkb(d, "pack", "change", "run")
print(out2)
if "modern.cc::new_user" in out:
    print("DEFECT: new_user() calls its own run(), but a macro `run` from legacy.h (never included by modern.cc)")
    print("        makes the pack say new_user reaches legacy_helper")
    sys.exit(1)
print("ok")
