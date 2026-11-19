import sys, os, json
sys.path.insert(0, "audit/repro")
import fx
body = "def helper(x):\n    return x * 2\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(3))
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": body,
                     "tests/test_a.py": "from pkg.a import helper\n\n\ndef test_h():\n    assert helper(1) == 2\n",
                     "docs/n.md": "call helper here\n"})
for c in sys.argv[1:]:
    g = c.startswith("G:")
    t = json.loads(c[2:]) if g else {"command": c}
    d, x = fx.hook(root, t, tool="Grep" if g else "Bash")
    print("===", c, "->", d)
    print(x)
    if not g:
        print("--- real:")
        print("\n".join(fx.grep_lines(root, c)))
