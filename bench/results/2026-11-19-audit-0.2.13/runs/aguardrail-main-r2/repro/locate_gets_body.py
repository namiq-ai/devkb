import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

src = "def helper(x):\n" + "".join(f"    y{i} = x + {i}\n" for i in range(40)) + "    return x\n"
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": src})
cmd = 'grep -rn "def helper" pkg'
dec, text = fx.hook(root, {"command": cmd})
real = "\n".join(fx.grep_lines(root, cmd))
print("decision:", dec, "| grep output", len(real), "chars; the answer", len(text), "chars,", len(text.splitlines()), "lines")
if dec == "deny" and len(text) > 3 * len(real) + 200:
    print("DEFECT: 'where is helper defined' (no -A/-B/-C) is replaced by the whole 40-line body, far larger than grep's one line (SPEC-DKB-007 R5, 'locate' = one location line)")
    sys.exit(1)
print("ok")
