"""The template name omits POLICY_PREREGISTER_POST, which changes the checkout's content: a template built without it is reused with it."""
import os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "bench" / "policy"))
import policybench as pb  # noqa: E402

pb.TEMPLATES = Path(tempfile.mkdtemp())
pb.sb.sh = lambda cmd, **kw: SimpleNamespace(stdout="a" * 40 + "\n")      # `git rev-parse` of the base commit
built = []


def fake_checkout(t, arm):
    t.mkdir(parents=True)
    built.append(os.environ.get("POLICY_PREREGISTER_POST"))


pb.checkout = fake_checkout
os.environ.pop("POLICY_PREREGISTER_POST", None)
a = pb.template_for("climain")
os.environ["POLICY_PREREGISTER_POST"] = "1"      # a ticket whose agent must write the PostToolUse hook
b = pb.template_for("climain")
print("template without the flag:", a.name, "| with the flag:", b.name, "| checkouts built:", len(built))
print("expected: two different templates (the flag adds a hook registration and a commit to the checkout)")
sys.exit(1 if a == b else 0)
