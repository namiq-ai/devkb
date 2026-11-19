"""A name search the hook replaces ("Complete") drops call sites grep would print: `uses` keeps 3 hits per file."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

body = "def helper(x):\n    return x\n\n\ndef main():\n" + "".join(f"    helper({i})\n" for i in range(8))
repo = fixture({"pkg/a.py": body})
cmd = 'grep -rn "helper" pkg'
real = grep(repo, cmd).splitlines()
kind, text = hook(repo, "Bash", cmd)
shown = [l for l in text.splitlines() if l.startswith("pkg/a.py:")]
print(f"grep prints {len(real)} lines; hook action={kind}; answer lists {len(shown)} of them")
print(text)
if kind == "deny" and len(shown) < len(real) and "more" not in text:
    print("DEFECT: the search was replaced by an answer that says Complete and silently leaves out",
          len(real) - len(shown), "lines grep would print")
    sys.exit(1)
print("ok")
