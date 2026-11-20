import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, hook, grep, PY, CK

A = "def alpha(x):\n    return x + 1\n\n\ndef beta(y):\n    return alpha(y)\n\n\nclass Gamma:\n    def run(self):\n        return alpha(2)\n"
repo = fixture({"a.py": A, "b.py": "from a import alpha\n\n\ndef use():\n    return alpha(3)\n", "uniq_name.py": "def uniq_name():\n    return 1\n\n\ndef caller():\n    return uniq_name()\n"})
print(subprocess.run([PY, "-m", "devkb.cli", "pack", "--project", str(repo), "change", "alpha"], capture_output=True, text=True, cwd=CK).stdout[:800])
for c in ['grep -rn alpha .', 'grep -rn "uniq_name" .', 'grep -rn uniq_name --include="*.js" .', 'grep -rn uniq_name -e other .',
          'grep -rn -e uniq_name -e caller .', 'grep -rn "uniq_name\\|caller" .', 'grep -rn "uniq_name|caller" .', 'grep -rnF "uniq_name|caller" .',
          'grep -rn UNIQ_NAME .']:
    act, text = bash(repo, c)
    print("===", c, "->", act, len(text or ""), "| grep", len(grep(repo, c)))
    if act == "deny":
        print(text)
