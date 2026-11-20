"""A JSON boolean passes as an item number (True == 1), so the posted comment names a duplicate of "#True"."""
import importlib.util, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
v = {"validity": "duplicate", "type": "bug", "priority": "low", "duplicate_of": True, "comment": "same"}
try:
    out = t.validate(v, {1, 2, 3}, 9)
except ValueError as e:
    print("rejected:", e)
    sys.exit(0)
print("accepted; comment:", t.comment_text(out).splitlines()[-4:])
print("expected: duplicate_of true is rejected (only an integer item number is accepted)")
sys.exit(1)
