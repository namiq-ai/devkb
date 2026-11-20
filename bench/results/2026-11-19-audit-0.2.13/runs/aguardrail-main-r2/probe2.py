import sys, os, tempfile
sys.path.insert(0, ".")
from pathlib import Path
from devkb import misses
d = Path(tempfile.mkdtemp())
(d / "a.cc").write_text("""#include <x>

namespace n {

int Foo::bar(int x)
{
  if (x) {
    return helper(x);
  }
  return 0;
}

static int g = helper(2);

struct S {
  int m() { return helper(1); }
};
}  // namespace n

int main() {
  return helper(3);
}
""")
txt = "\n".join(f"a.cc:{n}:{l}" for n, l in enumerate((d / "a.cc").read_text().splitlines(), 1) if "helper" in l)
r = misses.parse_grep(txt, names=["helper"], repo=d)
for m in r["matches"]:
    print(m)
r = misses.parse_grep("\n".join(l.split(":", 1)[1] for l in txt.splitlines()), names=["helper"], repo=d, single_file="a.cc")
print([m["at"] for m in r["matches"]])
