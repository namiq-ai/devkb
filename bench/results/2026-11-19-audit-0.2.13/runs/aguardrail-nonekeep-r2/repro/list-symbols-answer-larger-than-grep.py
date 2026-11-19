import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx
from fixture_files import FILES

repo, home = fx.make_repo(FILES)
cmd = 'grep -n "^class " pkg/mod.py'
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
ans = [l for l in text.splitlines() if l.startswith("L")]
print("grep prints", len(want), "line:", want)
print("decision:", dec)
print(text)
if len(ans) > len(want):
    print(f"DEFECT: the outline lists {len(ans)} symbols (constants, functions, methods) for a search that matches {len(want)} line(s)")
    sys.exit(1)
print("ok")
