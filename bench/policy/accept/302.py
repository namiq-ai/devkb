"""#302: the edit rule reads the path relative to the checkout root; a quoted --project fixture path counts like an
unquoted one. Black box on storybench.transcript and storybench.devkb_commands."""
import importlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sb = importlib.import_module("storybench")
sb.guardrail_actions = lambda s, log=None: (0, {})


def msg(i, tools):
    return {"type": "assistant", "message": {"id": f"m{i}", "usage": {"output_tokens": 1}, "content": [
        {"type": "tool_use", "id": f"t{i}{k}", "name": n, "input": inp} for k, (n, inp) in enumerate(tools)]}}


out = {}
cwd = "/home/u/devkb/bench/work/run-1"           # a checkout under a folder named devkb
lines = [{"type": "system", "subtype": "init", "session_id": "s", "cwd": cwd},
         msg(1, [("Edit", {"file_path": f"{cwd}/docs/notes.md"})]),
         msg(2, [("Bash", {"command": ".venv/bin/devkb outline devkb/x.py"})])]
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "stream.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    t = sb.transcript(p)
    out["parent_folder_named_devkb"] = (t["devkb_nav"], t["devkb_selftest"]) == (1, 0)
    lines[1] = msg(1, [("Edit", {"file_path": f"{cwd}/devkb/cli.py"})])
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    t = sb.transcript(p)
    out["a_real_devkb_edit_still_counts"] = (t["devkb_nav"], t["devkb_selftest"]) == (0, 1)
out["quoted_project_is_a_fixture"] = all(
    sb.devkb_commands(f"devkb symbol foo --project {q}") == (0, 1) for q in ("/tmp/fx", '"/tmp/fx"', "'/tmp/fx'"))
out["pass"] = all(out.values())
print(json.dumps(out))
