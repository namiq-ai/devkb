"""#306: re-scoring one arm (POLICY_ARMS) replaces only that arm's rows in results-ISSUE.jsonl. Black box on policybench.score."""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(W / "bench" / "policy"))
pb = importlib.import_module("policybench")


def row(arm, rep, tag):
    return {"run": f"p9-{arm}-r{rep}", "issue": "9", "arm": arm, "rep": str(rep), "acceptance": {"pass": True}, "suite_pass": True,
            "cost": 0.1, "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": [], "tag": tag}


res = {}
with tempfile.TemporaryDirectory() as td:
    pb.B = Path(td)
    for arm in ("none", "main"):
        for rep in (1, 2):
            d = Path(td) / "runs" / f"p9-{arm}-r{rep}"
            d.mkdir(parents=True)
            (d / "end").write_text(json.dumps({"exit": 0, "seconds": 1}))
    pb.score_run = lambda issue, out: row(out.name.split("-")[1], out.name.split("-")[2][1:], "new")
    old = [row("none", 1, "old"), row("none", 2, "old"), row("main", 1, "old"), row("main", 2, "old")]
    (Path(td) / "results-9.jsonl").write_text("".join(json.dumps(r) + "\n" for r in old))
    os.environ["POLICY_ARMS"] = "main"
    pb.score(["9"])
    got = [json.loads(l) for l in (Path(td) / "results-9.jsonl").read_text().splitlines() if l.strip()]
    res["other_arm_rows_kept"] = sorted((r["arm"], r["tag"]) for r in got if r["arm"] == "none") == [("none", "old"), ("none", "old")]
    res["rescored_arm_rows_replaced"] = sorted((r["arm"], r["tag"]) for r in got if r["arm"] == "main") == [("main", "new"), ("main", "new")]
    res["no_duplicates"] = len(got) == 4
res["pass"] = all(res.values())
print(json.dumps(res))
