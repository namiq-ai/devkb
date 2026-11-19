import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx
from fixture_files import FILES

repo, home = fx.make_repo(FILES)
bad = 0
for tool, inp in (("Bash", {"command": "grep -rn handler pkg | head -2"}),
                  ("Grep", {"pattern": "handler", "path": "pkg", "output_mode": "content", "head_limit": 2})):
    dec, text = fx.guard(repo, home, tool, inp, sid="t" + tool)
    n = len(fx.lines_of(text))
    print(tool, inp, "->", dec, "; answer lines:", n, "; the search was limited to 2 lines")
    if dec == "deny" and n > 2:
        bad += 1
if bad:
    print("DEFECT: the answer is larger than the 2 lines the limited search would print")
    sys.exit(1)
print("ok")
