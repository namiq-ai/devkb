import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, hook, grep

files = {"a.py": "def alpha(x):\n    return x + 1\n\n\ndef beta(y):\n    # alpha is called here\n    return alpha(y)\n\n\nNAME = 'alpha'\n",
         "docs/n.md": "alpha does things\n", "c.py": "def other():\n    return alpha(1)\n"}
repo = fixture(files)
for c, t in [('grep -rn alpha a.py c.py docs', 0), ('grep -rn alpha --include="*.py" .', 0), ('grep -rnw alpha --exclude-dir=.devkb .', 0),
             ('grep -rnl alpha --exclude-dir=.devkb .', 0), ('grep -rn --exclude-dir=.devkb alpha .', 0), ('grep -rn "alpha" . --exclude-dir=.devkb', 0)]:
    act, text = bash(repo, c)
    print("===", c, "->", act, len(text or ""), "| grep", len(grep(repo, c)))
    if act == "deny":
        print(text)
        print("GREP:\n" + grep(repo, c))
