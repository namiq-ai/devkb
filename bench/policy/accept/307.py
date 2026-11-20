"""#307: every setting that changes a checkout's content is part of the template key (POLICY_PREREGISTER_POST). Black box on
policybench.template_for with the checkout stubbed."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(W / "bench" / "policy"))
pb = importlib.import_module("policybench")
pb.sb.REPO = Path(__file__).resolve().parents[3]
for k in list(pb.BASES):
    pb.BASES[k] = "HEAD"
res = {}
with tempfile.TemporaryDirectory() as td:
    pb.TEMPLATES = Path(td)
    built = []

    def fake_checkout(t, arm):
        built.append(Path(t).name)
        Path(t).mkdir(parents=True)

    pb.checkout = fake_checkout
    os.environ.pop("POLICY_PREREGISTER_POST", None)
    a = pb.template_for("climain")
    again = pb.template_for("climain")
    os.environ["POLICY_PREREGISTER_POST"] = "1"
    b = pb.template_for("climain")
    res["same_setting_reuses_the_template"] = a == again and built.count(a.name) == 1
    res["a_different_setting_gets_its_own_template"] = a != b and b.name in built
res["pass"] = all(res.values())
import json
print(json.dumps(res))
