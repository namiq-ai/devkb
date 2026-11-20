"""listing_then_read counts reads of files outside the working directory as reads in the listed folder after a bare `ls`."""
import json, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "bench" / "exploration"))
import listing_then_read as l  # noqa: E402

d = Path(tempfile.mkdtemp()) / "run1"
d.mkdir()
ev = [{"type": "system", "subtype": "init", "cwd": "/work/proj"}]


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "x", "name": name, "input": inp}]}}


ev += [use("Bash", {"command": "ls"}), use("Read", {"file_path": "/usr/lib/python3/other_project.py"}),
       use("Bash", {"command": "cat /usr/lib/python3/other_project2.py"})]
(d / "stream.jsonl").write_text("\n".join(map(json.dumps, ev)) + "\n")
r = l.measure(d.parent, 5)
print("reads after the listing of /work/proj:", r["reads_after_listings"], "(expected 0: both files are outside it)")
sys.exit(1 if r["reads_after_listings"] else 0)
