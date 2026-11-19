import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({
    "a.h": "#define CALL_FREE(x) free_fn(x)\nvoid free_fn(int);\n",
    "a.cc": '#include "a.h"\nvoid free_fn(int) {}\n',
    "u.cc": '#include "a.h"\nvoid user() { CALL_FREE(3); }\n',
})
_fx.build(d)
out, _ = _fx.dk(d, "pack", "--project", ".", "change", "free_fn")
print(out[out.find("## Functions"):][:900])
reached = "u.cc::user" in out
stale = "no preprocessor expansion" in out
print("macro call attributed:", reached, "| footer says 'no preprocessor expansion':", stale)
print("expected: the pack's C/C++ limits note says repository macros ARE expanded (#118) and names what is still not")
sys.exit(1 if (reached and stale) else 0)
