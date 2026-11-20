"""When a name is defined in two files, a definition search naming the second file is denied without the body (only the
first match carries source), with a false reason ("is its end is not known") for a 3-line function with a known span."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

repo = fixture({"a.py": "def helper(x):\n    return x + 1\n", "b.py": "def helper(x):\n    y = x * 2\n    return y\n"})
cmd = 'grep -n "def helper" -A5 b.py'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
print("grep prints:\n" + real + f"hook action={kind}:\n" + text)
if kind == "deny" and ("return y" not in text or "is its end" in text):
    print("DEFECT: denied a 3-line body grep would print; the answer says 'its end is not known' (the span is exact)")
    sys.exit(1)
print("ok")
