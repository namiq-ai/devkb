import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from pathlib import Path
from devkb import misses

d = Path(tempfile.mkdtemp())
(d / "a.cc").write_text("int Foo::bar(int x)\n{\n  if (x) {\n    return helper(x);\n  }\n  return 0;\n}\n")
r = misses.parse_grep("a.cc:4:    return helper(x);", names=["helper"], repo=d)
got = r["matches"][0]["in"]
print("enclosing function of a.cc:4 (inside `int Foo::bar(int x)` with the brace on the next line):", repr(got))
if "bar" not in got:
    print("DEFECT: the text scan names no enclosing function for Allman-style (brace on its own line) C/C++ bodies; expected 'Foo::bar'")
    sys.exit(1)
print("ok")
