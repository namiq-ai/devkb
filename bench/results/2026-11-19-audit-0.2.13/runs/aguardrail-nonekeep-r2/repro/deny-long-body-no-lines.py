import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx

body = "".join(f"    step{i} = {i} * 2\n" for i in range(120))
repo, home = fx.make_repo({"pkg/big.py": "def build_everything(x):\n" + body + "    return x\n"})
cmd = 'grep -n "def build_everything" -A30 pkg/big.py'
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
print("grep prints", len(want), "lines (the definition and 30 lines of its body)")
print("decision:", dec)
print(text)
shown = [l for l in text.splitlines() if "step0" in l or "step1 " in l]
if dec == "deny" and not shown:
    print("DEFECT: the search is denied and the answer has none of the 30 body lines the agent asked for")
    sys.exit(1)
print("ok")
