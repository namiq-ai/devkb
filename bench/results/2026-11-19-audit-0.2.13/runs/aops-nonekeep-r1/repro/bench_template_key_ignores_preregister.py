"""A template built without POLICY_PREREGISTER_POST must not be reused by a batch that sets it: the checkout differs."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import policybench as pb

tmp = Path(tempfile.mkdtemp())
pb.TEMPLATES = tmp / "templates"
pb.BASES["before"] = "HEAD"
built = []


def fake_checkout(w, arm):
    w.mkdir(parents=True)
    (w / "settings").write_text("post-hook registered" if os.environ.get("POLICY_PREREGISTER_POST") == "1" else "no post hook")
    built.append(w)


pb.checkout = fake_checkout
os.environ.pop("POLICY_PREREGISTER_POST", None)
t1 = pb.template_for("before")
os.environ["POLICY_PREREGISTER_POST"] = "1"
t2 = pb.template_for("before")
print("batch 1 template:", t1.name, "->", (t1 / "settings").read_text())
print("batch 2 (POLICY_PREREGISTER_POST=1) template:", t2.name, "->", (t2 / "settings").read_text(), "| builds:", len(built))
print("expected: batch 2 gets a checkout with the post hook registered; actual: the template of batch 1 is reused")
sys.exit(1 if (t2 / "settings").read_text() != "post-hook registered" else 0)
