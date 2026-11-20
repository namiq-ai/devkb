"""`policybench.py score ISSUE` with POLICY_ARMS set rewrites results-ISSUE.jsonl (the release table's input) with only
that arm's rows, silently dropping every other arm's scored runs."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import policybench as pb  # noqa: E402

tmp = Path(tempfile.mkdtemp())
pb.B = tmp
(tmp / "accept").mkdir()
acc = tmp / "accept" / "7.py"
acc.write_text("print('{}')\n")
sha = hashlib.sha256(acc.read_bytes()).hexdigest()
for arm in ("none", "main"):
    out = tmp / "runs" / f"p7-{arm}-r1"
    out.mkdir(parents=True)
    (out / "end").write_text(json.dumps({"exit": 0, "seconds": 1}))
    row = {"run": out.name, "issue": "7", "arm": arm, "rep": "1", "accept_sha256": sha, "acceptance": {"pass": True},
           "suite_pass": True, "cost": 1.0, "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": []}
    (out / "score.json").write_text(json.dumps(row) + "\n")
os.environ["POLICY_ARMS"] = "main"
pb.score(["7"])
rows = [json.loads(l) for l in (tmp / "results-7.jsonl").read_text().splitlines()]
print("arms in results-7.jsonl after scoring only the 'main' arm:", [r["arm"] for r in rows], "(scored runs on disk: none, main)")
print("expected: the other arm's rows are kept, so release_table.py still has its baseline")
sys.exit(1 if {r["arm"] for r in rows} != {"none", "main"} else 0)
