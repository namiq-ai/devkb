import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({
    "w.h": "struct W { void draw(int x); void draw(int x, int y); };\n",
    "w.cc": '#include "w.h"\nvoid W::draw(int x) {}\nvoid W::draw(int x, int y) {}\n',
    "u.cc": '#include "w.h"\nvoid u(W& w) { w.draw(1); }\n',
})
_fx.build(d)
out, _ = _fx.dk(d, "pack", "--project", ".", "refactor", "W::draw")
print(out[:600])
choices = re.findall(r"^- `([^`]+)`", out, re.M)
bad = "cannot resolve" in out and len(choices) != len(set(choices))
print("choices offered:", choices)
print("BAD: the pack lists identical names (no line, no signature), so 'Pass one as path::name' cannot tell them apart" if bad else "ok")
print("expected: each choice distinguishable (e.g. path:line or signature), or a pack that covers all overloads")
sys.exit(1 if bad else 0)
