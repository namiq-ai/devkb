"""A checkout template is keyed by arm, base commit and devkb commit only; checkout() also depends on
POLICY_PREREGISTER_POST, so a template built without it is reused when it is set (and the PostToolUse hook the story
needs is never registered)."""
import os, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import policybench as pb  # noqa: E402

tmp = Path(tempfile.mkdtemp())
pb.TEMPLATES = tmp / "templates"
pb.toolenv.ENVS = tmp / "toolenvs"
pb.BASES["nonekeep"] = "HEAD"
built = []


def fake_checkout(w, arm):
    w.mkdir(parents=True)
    built.append(os.environ.get("POLICY_PREREGISTER_POST"))


pb.checkout = fake_checkout
os.environ.pop("POLICY_PREREGISTER_POST", None)
a = pb.template_for("nonekeep")
os.environ["POLICY_PREREGISTER_POST"] = "1"
b = pb.template_for("nonekeep")
print("template 1:", a.name, "template 2:", b.name, "checkouts built with POLICY_PREREGISTER_POST =", built)
print("expected: the run that sets POLICY_PREREGISTER_POST=1 gets a template built with it (2 builds)")
sys.exit(1 if len(built) == 1 else 0)
