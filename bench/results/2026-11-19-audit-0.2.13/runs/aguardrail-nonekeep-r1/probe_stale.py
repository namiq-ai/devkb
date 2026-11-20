import sys, time, os
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "repro"))
from _fx import fixture, hook, grep
repo = fixture({"m.py": "def helper(x):\n    return x\n", "u.py": "from m import helper\n\n\ndef go():\n    return helper(1)\n"})
# a file edited after the build, outside the searched scope, then the search in a scope
(repo / "sub").mkdir()
(repo / "sub" / "w.py").write_text("from m import helper\nhelper(2)\n")
for cmd in ['grep -rn "helper" .', 'grep -rn "helper" sub', 'grep -rn "helper" . --include=u.py', 'grep -n "helper" u.py', 'grep -rn "helper" . | grep -v "^./m"']:
    print(cmd, "| grep prints", len(grep(repo, cmd).splitlines()), "->", *hook(repo, "Bash", cmd)[:1], hook(repo, "Bash", cmd)[1][:300].replace("\n", " / "))
