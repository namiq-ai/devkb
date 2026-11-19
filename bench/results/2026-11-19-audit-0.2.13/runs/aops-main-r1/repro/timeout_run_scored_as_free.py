"""A run that hit the 5400 s timeout (or was killed) has no `result` event: transcript() gives cost 0 and context 0,
and the release table averages those zeros in, so the arm looks cheaper than it was."""
import json, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import storybench as sb  # noqa: E402
p = Path(tempfile.mkdtemp()) / "stream.jsonl"
ev = [{"type": "system", "subtype": "init", "session_id": "s", "cwd": "/w"}]
for i in range(40):
    ev.append({"type": "assistant", "message": {"id": f"m{i}", "content": [{"type": "text", "text": "x"}],
               "usage": {"input_tokens": 10, "cache_read_input_tokens": 50000, "cache_creation_input_tokens": 500, "output_tokens": 800}}})
p.write_text("".join(json.dumps(e) + "\n" for e in ev))       # no result event: the run was cut off
r = sb.transcript(p)
print("turns", r["turns"], "cost", r["cost"], "ctx_tokens", r["ctx_tokens"], "out_tokens", r["out_tokens"])
print("expected: a cut-off run's cost and context are not recorded as 0 (estimated from the messages' usage, or the run flagged)")
sys.exit(1 if r["turns"] and not r["ctx_tokens"] else 0)
