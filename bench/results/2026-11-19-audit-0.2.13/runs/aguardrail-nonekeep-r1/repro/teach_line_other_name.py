"""D1 (#267): the answer ends with the devkb command that gives it. For `grep -n "alpha_sym\\|beta_key" f.py` the answer
is about the string key beta_key, but the teach line names the first name, alpha_sym (a different answer)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

src = ('def alpha_sym(d):\n    return d\n\n\ndef go(row):\n    row["beta_key"] = 1\n    return row.get("beta_key"), alpha_sym(row)\n')
repo = fixture({"m.py": src, "n.py": "from m import alpha_sym\n\n\ndef other():\n    return alpha_sym({})\n"})
cmd = 'grep -rn "alpha_sym\\|beta_key" . | head'
kind, text = hook(repo, "Bash", cmd)
print(f"hook {kind}:\n{text}")
teach = [l for l in text.splitlines() if l.startswith("Next time")]
if kind != "none" and "beta_key" in text.split("Next time")[0] and teach and "beta_key" not in teach[0]:
    print("DEFECT: the answer is about beta_key; the teach line gives the command for alpha_sym:", teach[0])
    sys.exit(1)
print("ok (or the fixture did not reach the key answer)")
