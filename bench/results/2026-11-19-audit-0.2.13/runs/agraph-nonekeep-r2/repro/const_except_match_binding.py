import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _fx
src = '''K1 = 1
K2 = 2

def e1():
    try:
        pass
    except Exception as K1:
        return K1

def e2(x):
    match x:
        case [K2, _]:
            return K2
'''
d = _fx.make({"m.py": src})
_fx.build(d)
bad = False
for k, what in (("K1", "`except ... as K1` binding"), ("K2", "`case [K2, _]` capture")):
    out, _ = _fx.dk(d, "pack", "--project", ".", "change", k)
    uses = out[out.find("## Uses"):out.find("## Test")]
    print(k, uses.strip().replace("\n", " "))
    if "m.py:" in uses and "none the graph" not in uses:
        print(f"BAD: a local {what} is attributed as a read of the module constant {k}")
        bad = True
print("expected: no uses of K1 / K2 (the reads are of function-local names)")
sys.exit(1 if bad else 0)
