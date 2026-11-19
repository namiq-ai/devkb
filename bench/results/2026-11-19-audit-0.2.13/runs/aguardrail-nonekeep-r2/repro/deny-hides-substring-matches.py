import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx

core = "def fetch_rows(x):\n    return [x]\n"
app = "import core\n\n\ndef run():\n    a = core.fetch_rows(1)\n    b = core.fetch_rows(2)\n"
other = "def prefetch_rows(x):\n    return x\n\n\nstop_fetch_rows = False\n"
repo, home = fx.make_repo({"lib/core.py": core, "lib/app.py": app, "lib/other.py": other})
cmd = "grep -rn fetch_rows lib"          # plain grep: substring match, so prefetch_rows and stop_fetch_rows match too
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
got = {l.replace(" ", "") for l in fx.lines_of(text)}
missing = [l for l in want if l.replace(" ", "") not in got]
print("decision:", dec)
print(text)
print("grep prints", len(want), "lines; lines grep prints that the denied answer lacks:", missing)
if dec == "deny" and missing:
    print("DEFECT: the search is replaced by an answer that hides lines grep would print (substring matches)")
    sys.exit(1)
print("ok")
