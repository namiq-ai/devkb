"""Acceptance of #117 (SPEC-DKB-004 story 1) on one finished run's checkout: prints one JSON line.

Checks what the ticket's "Done when" can check mechanically; the hand verdicts are read, not re-judged."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

w = Path(sys.argv[1])
py = str(w / ".venv" / "bin" / "python")
out = {}
with tempfile.TemporaryDirectory() as td:
    t = Path(td) / "truth_cJSON.json"
    p = subprocess.run([py, "bench/cpp/truth_clang.py", "corpus/cJSON", str(t)], cwd=w, capture_output=True, text=True,
                       timeout=1200)
    if p.returncode == 0 and t.exists():
        d = json.loads(t.read_text())
        out["truth_recursive_edges"] = sum(1 for a, b in d.get("edges", []) if a == b)
        out["truth_lists_failed_files"] = any(k for k in d if re.search(r"fail|not_measured|skipped|unparsed", k))
        q = subprocess.run([py, "bench/cpp/quality.py", ".", "corpus/cJSON", str(t)], cwd=w, capture_output=True,
                           text=True, timeout=1200)
        try:
            qj = json.loads(q.stdout.strip().splitlines()[-1])
            out["quality_precision_cJSON"] = qj.get("edge_precision")
            out["quality_reports_not_measured"] = any("not_measured" in k for k in qj)
        except (ValueError, IndexError):
            out["quality_error"] = (q.stderr or q.stdout)[-300:]
    else:
        out["truth_error"] = (p.stderr or p.stdout)[-300:]
out["adjudicate_py"] = (w / "bench" / "cpp" / "adjudicate.py").exists()
s = w / "docs" / "specs" / "cpp-precision-sample.md"
txt = s.read_text() if s.exists() else ""
out["precision_sample_md"] = bool(txt)
out["sample_covers"] = [r for r in ("cJSON", "leveldb", "fmt") if r in txt]
out["sample_has_interval"] = bool(re.search(r"95\s*%|interval|Wilson", txt, re.I))
verdicts = list(w.rglob("*adjudicat*.jsonl")) + list(w.rglob("*verdict*.jsonl"))
out["verdict_rows"] = sum(sum(1 for _ in open(v)) for v in verdicts if ".venv" not in str(v))
out["pass"] = bool(out.get("truth_recursive_edges", 0) > 0 and out.get("quality_reports_not_measured")
                   and out["adjudicate_py"] and len(out["sample_covers"]) == 3 and out["sample_has_interval"]
                   and out["verdict_rows"] >= 300)
print(json.dumps(out))
