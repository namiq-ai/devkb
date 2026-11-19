import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

src = ("import asyncio\n\n\ndef a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    # async note\n    return 3\n")
root = fx.make_repo({"pkg/__init__.py": "", "pkg/m.py": src})
for cmd in ('grep -n "async" pkg/m.py', 'grep -n "static" pkg/m.py', 'grep -n "public" pkg/m.py', 'grep -n "function" pkg/m.py'):
    dec, text = fx.hook(root, {"command": cmd})
    real = fx.grep_lines(root, cmd)
    print(cmd, "| grep prints", real, "| answer:", text.splitlines()[1:4])
    if "function a" in text:
        print("DEFECT: a search for the word in %r (a literal) is answered with the file's whole outline: not what the search asked" % cmd)
        sys.exit(1)
print("ok")
