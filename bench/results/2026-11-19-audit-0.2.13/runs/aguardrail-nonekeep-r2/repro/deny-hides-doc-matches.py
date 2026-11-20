import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx
from fixture_files import FILES

repo, home = fx.make_repo(FILES)
cmd = "grep -rn handler pkg docs"       # the agent names the docs folder itself
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
got = {l.replace(" ", "") for l in fx.lines_of(text)}
missing = [l for l in want if l.replace(" ", "") not in got]
print("decision:", dec)
print(text)
print("lines grep prints that the denied answer lacks:", missing)
if dec == "deny" and missing:
    print("DEFECT: a search that names a docs folder is replaced by an answer without the docs lines")
    sys.exit(1)
print("ok")
