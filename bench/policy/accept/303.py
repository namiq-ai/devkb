"""#303: a run cut off by the timeout (no final result message) is not recorded with cost 0 and context 0: its context
is estimated from the messages' usage and its cost is estimated or flagged. Black box on storybench.transcript."""
import importlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sb = importlib.import_module("storybench")
sb.guardrail_actions = lambda s, log=None: (0, {})


def msg(i, usage):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": usage, "content": []}}


rows = [{"type": "system", "subtype": "init", "session_id": "s"},
        msg(1, {"input_tokens": 5, "cache_read_input_tokens": 1000, "output_tokens": 10}),
        msg(2, {"input_tokens": 7, "cache_read_input_tokens": 3000, "cache_creation_input_tokens": 100, "output_tokens": 20})]
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in rows))
    t = sb.transcript(p)
flagged = any(v is True for k, v in t.items() if k not in ("calls", "chars"))
out = {"context_estimated": t["ctx_tokens"] > 0, "cost_not_zero_or_flagged": (t["cost"] not in (0, 0.0)) or flagged}
fin = rows + [{"type": "result", "total_cost_usd": 0.5, "usage": {"input_tokens": 9}, "modelUsage": {}}]
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in fin))
    t2 = sb.transcript(p)
out["finished_run_unchanged"] = t2["cost"] == 0.5 and not any(v is True for k, v in t2.items() if k not in ("calls", "chars"))
out["pass"] = all(out.values())
print(json.dumps(out))
