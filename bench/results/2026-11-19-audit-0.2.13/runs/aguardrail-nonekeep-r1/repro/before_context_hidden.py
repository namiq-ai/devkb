"""`grep -n "def target" -B3 -A4 m.py` prints the decorator and comment lines above the definition. The hook denies the
search and answers from the `def` line on, so the lines grep was asked to print above it are gone."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

src = "import functools\n\n\n# cache every result\n@functools.lru_cache(maxsize=None)\ndef target(a):\n    b = a + 1\n    return b\n"
repo = fixture({"m.py": src})
for cmd in ('grep -n "def target" -B3 -A4 m.py', 'grep -n "def target" -B2 m.py'):
    real = grep(repo, cmd)
    kind, text = hook(repo, "Bash", cmd)
    print(f"{cmd}\ngrep prints:\n{real}hook {kind}:\n{text}\n")
    if kind == "deny" and "lru_cache" in real and "lru_cache" not in text:
        print("DEFECT: the lines above the definition that -B asked for are missing from the replacement")
        sys.exit(1)
print("ok")
