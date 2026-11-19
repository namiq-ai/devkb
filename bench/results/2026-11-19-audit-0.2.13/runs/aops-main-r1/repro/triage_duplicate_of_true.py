"""validate() accepts duplicate_of=true (bool is an int, and True == 1 is in the known set) and posts '#True'."""
import importlib.util, os, sys, tempfile
from pathlib import Path
os.environ["TRIAGE_HOME"] = tempfile.mkdtemp()
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", root / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
try:
    v = t.validate({"validity": "duplicate", "type": "bug", "priority": "low", "duplicate_of": True, "comment": "dup"}, {1, 2}, 5)
except ValueError as e:
    print("rejected:", e); sys.exit(0)
text = t.comment_text(v)
print("accepted; posted text contains:", [l for l in text.splitlines() if "duplicate" in l])
print("expected: a boolean is not an item number; the verdict is refused")
sys.exit(1)
