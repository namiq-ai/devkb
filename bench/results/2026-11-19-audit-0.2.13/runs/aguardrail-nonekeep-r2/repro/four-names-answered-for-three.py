import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx

src = {
    "lib/a.py": "def alpha_one():\n    return 1\n\n\ndef beta_two():\n    return 2\n\n\ndef gamma_three():\n    return 3\n\n\ndef delta_four():\n    return 4\n",
    "lib/use.py": "from lib.a import alpha_one, beta_two, gamma_three, delta_four\n\n\ndef go():\n    return alpha_one() + beta_two() + gamma_three() + delta_four()\n",
}
repo, home = fx.make_repo(src)
cmd = r"grep -rn 'alpha_one\|beta_two\|gamma_three\|delta_four' lib"
want = fx.grep_out(repo, cmd)
dec, text = fx.guard(repo, home, "Bash", {"command": cmd})
got = {l.replace(" ", "") for l in fx.lines_of(text)}
missing = [l for l in want if l.replace(" ", "") not in got]
print("grep prints", len(want), "lines; decision:", dec)
print(text)
print("lines grep prints that the answer lacks:", missing)
if dec == "deny" and any("delta_four" in m for m in missing):
    print("DEFECT: the fourth name is dropped (names are cut to 3) yet the search is replaced and called Complete")
    sys.exit(1)
print("ok")
