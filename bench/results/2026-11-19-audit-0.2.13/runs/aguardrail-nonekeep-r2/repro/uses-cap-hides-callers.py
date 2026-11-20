import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx

core = "def compute_total(x):\n    return x + 1\n"
many = "import lib.core as core\n\n\ndef run():\n" + "".join(f"    y{i} = core.compute_total({i})\n" for i in range(8))
mine = "import lib.core as core\n\n\ndef go():\n" + "".join(f"    z{i} = core.compute_total({i})\n" for i in range(3))
repo, home = fx.make_repo({"lib/core.py": core, "aaa/many.py": many, "zzz/mine.py": mine})
cmd = "grep -rn compute_total aaa"
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
got = fx.lines_of(text)
norm = lambda ls: sorted(l.replace(" ", "") for l in ls)
print("grep prints", len(want), "lines; guardrail decision:", dec, "; answer carries", len(got), "lines")
print(text)
if dec == "deny" and norm(got) != norm(want):
    print("DEFECT: the search is denied and its answer ('Complete') leaves out call sites grep would print")
    sys.exit(1)
print("ok")
