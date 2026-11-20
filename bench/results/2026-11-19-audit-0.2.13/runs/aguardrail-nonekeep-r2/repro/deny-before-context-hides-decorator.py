import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx
from fixture_files import FILES

repo, home = fx.make_repo(FILES)
cmd = 'grep -n "def handler" -B3 pkg/mod.py'
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
print("grep prints:", want)
print("decision:", dec)
print(text)
if dec == "deny" and "@decorator" not in text:
    print("DEFECT: -B3 asked for the 3 lines before the definition (the decorator); the denied answer starts at the def line")
    sys.exit(1)
print("ok")
