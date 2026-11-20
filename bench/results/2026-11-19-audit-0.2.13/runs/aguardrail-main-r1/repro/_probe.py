import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, hook, grep

A = "def alpha(x):\n    return x + 1\n\n\ndef beta(y):\n    return alpha(y)\n\n\nclass Gamma:\n    def run(self):\n        return alpha(2)\n"
B = "from a import alpha\n\n\ndef use():\n    return alpha(3)  # alpha | beta\n"
repo = fixture({"a.py": A, "b.py": B, "sub/c.py": "from a import alpha\n\n\ndef deep():\n    return alpha(4)\n",
                "x.js": "function alpha() { return 1 }\nalpha()\n", "README.md": "alpha is a function\n"})
cases = [
    ("Bash", 'grep -rn "Alpha" .'), ("Bash", 'grep -rn -e alpha -e beta .'), ("Bash", r'grep -rn "alpha\|beta" .'),
    ("Bash", 'grep -rnF "alpha|beta" .'), ("Bash", 'grep -rn "alpha|beta" .'), ("Bash", 'grep -rn --include="*.js" alpha .'),
    ("Bash", 'grep -rn --include=*.md alpha .'), ("Bash", 'grep -A3 -c "def alpha" a.py'), ("Bash", 'grep -A3 -l "def alpha" a.py'),
    ("Bash", 'grep -A3 -v "def alpha" a.py'), ("Bash", 'grep -rn alpha b.py'), ("Bash", 'grep -rn "def " a.py'),
    ("Bash", 'cd sub && grep -n "def deep" c.py'), ("Bash", 'grep -rnc alpha .'), ("Bash", 'grep -rl alpha .'),
    ("Bash", 'grep -rn "return" .'), ("Bash", 'grep -rnw alpha .'), ("Bash", 'grep -rni ALPHA .'),
    ("Bash", 'grep -rn "alpha(" .'), ("Bash", 'grep -rn "^def alpha" .'), ("Bash", 'grep -rn "def alpha" . | head -1'),
    ("Grep", dict(pattern="alpha", output_mode="content", type="js")), ("Grep", dict(pattern="alpha", glob="*.md", output_mode="content")),
    ("Grep", dict(pattern="alpha", output_mode="count")), ("Grep", dict(pattern="alpha", output_mode="files_with_matches")),
    ("Grep", dict(pattern="alpha", output_mode="content", head_limit=1)), ("Grep", dict(pattern="alpha", output_mode="content", multiline=True)),
    ("Grep", dict(pattern="Alpha", output_mode="content", **{"-i": True})), ("Grep", dict(pattern="def alpha", output_mode="content", **{"-B": 2})),
]
for t, c in cases:
    inp = dict(command=c) if t == "Bash" else c
    act, text = hook(repo, t, inp)
    print("=== %s %s\n--> %s | %d chars" % (t, c, act, len(text or "")))
    if act in ("deny", "context") and not (text or "").startswith("devkb guardrail"):
        print(text[:600])
    if t == "Bash" and "cd " not in c:
        print("  [grep prints %d chars]" % len(grep(repo, c)))
