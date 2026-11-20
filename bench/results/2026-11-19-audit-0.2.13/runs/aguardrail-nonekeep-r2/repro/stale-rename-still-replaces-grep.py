import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx
from fixture_files import FILES

repo, home = fx.make_repo(FILES)
subprocess.run(["git", "mv", "pkg/use.py", "pkg/client.py"], cwd=repo, check=True)   # staged rename after the build
cmd = "grep -rn handler pkg"
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
print("grep prints:", want)
print("decision:", dec)
print(text)
if dec == "deny":
    print("DEFECT: the graph predates the rename (pkg/use.py -> pkg/client.py); the search is still replaced, "
          "and the answer leaves out every line grep prints from pkg/client.py")
    sys.exit(1)
print("ok")
