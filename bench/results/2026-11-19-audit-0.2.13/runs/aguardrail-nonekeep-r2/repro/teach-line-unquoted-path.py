import re
import shlex
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx

src = {"my dir/with space.py": "def spaced_fn():\n    return 1\n\n" + "".join(f"x{i} = 1\n" for i in range(130))}
repo, home = fx.make_repo(src)
dec, text = fx.guard(repo, home, "Bash", {"command": "grep -n '^def ' 'my dir/with space.py'"})
m = re.search(r"Next time ask devkb directly: `([^`]+)`", text)
print(dec)
print(text)
if not m:
    print("no teach line")
    sys.exit(1)
words = shlex.split(m.group(1))
print("teach command words:", words)
if words[:3] != ["devkb", "outline", "my dir/with space.py"]:
    print("DEFECT: the suggested command is not runnable as written: the path with a space is not quoted")
    sys.exit(1)
print("ok")
