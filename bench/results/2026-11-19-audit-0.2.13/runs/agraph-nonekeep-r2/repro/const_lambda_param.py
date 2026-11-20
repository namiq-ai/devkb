import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
d = _fx.make({"m.py": "OTHER = 6\n\ndef f():\n    return (lambda OTHER: OTHER)(1)\n\ndef g(xs):\n    return [OTHER for OTHER in xs]\n"})
_fx.build(d)
out, _ = _fx.dk(d, "pack", "--project", ".", "change", "OTHER")
print(out[out.find("## Functions"):out.find("## Test")])
bad = "m.py::f" in out
print("BAD: `f` is listed as reading the module constant OTHER, but line 4 reads the lambda's own parameter" if bad else "ok")
print("expected: no function reaches OTHER (comprehension variable is already handled, lambda parameter is not)")
sys.exit(1 if bad else 0)
