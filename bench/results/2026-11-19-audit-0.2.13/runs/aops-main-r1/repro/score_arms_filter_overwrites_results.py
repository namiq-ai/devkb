"""`policybench.py score ISSUE` with POLICY_ARMS=after rewrites results-ISSUE.jsonl (the input of release_table.py) and
results-policy.jsonl with only that arm: every other arm's scored runs vanish from the files."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import policybench as pb  # noqa: E402
tmp = Path(tempfile.mkdtemp())
pb.B = tmp
(tmp / "accept").mkdir()
acc = tmp / "accept" / "1.py"; acc.write_text("print('{}')\n")
sha = hashlib.sha256(acc.read_bytes()).hexdigest()
for arm in ("before", "after"):
    out = tmp / "runs" / f"p1-{arm}-r1"; out.mkdir(parents=True)
    (out / "end").write_text(json.dumps({"exit": 0, "seconds": 1}))
    (out / "score.json").write_text(json.dumps({"run": out.name, "issue": "1", "arm": arm, "accept_sha256": sha, "suite_pass": True,
        "acceptance": {"pass": True}, "cost": 1.0, "devkb_queries": 0, "guardrail_fired": 0, "dogfood_log": []}) + "\n")
os.environ["POLICY_ARMS"] = "after"
pb.score(["1"])
arms = [json.loads(l)["arm"] for l in (tmp / "results-1.jsonl").read_text().splitlines()]
print("arms in results-1.jsonl after scoring with POLICY_ARMS=after:", arms)
print("expected: both arms stay in the results file (the filter limits what is re-scored, not what is kept)")
sys.exit(1 if "before" not in arms else 0)
