"""#399: `pack error` lists only functions that hold the message; text no code raises gets an explicit "no function" answer. Black box on the checkout's own devkb (python bench/policy/accept/399.py CHECKOUT)."""
import json, subprocess, sys, tempfile
from pathlib import Path
W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
R = Path(tempfile.mkdtemp())
(R / "pkg").mkdir()
(R / "pkg" / "rx.py").write_text("def compile_pattern(q):\n    try:\n        return q\n    except ValueError as e:\n        raise ValueError(f\"bad regular expression: {e}\")\n")
(R / "pkg" / "other.py").write_text("def a(x):\n    raise ValueError('expression is too long for this regular tenant')\n\n\ndef b(x):\n    raise KeyError(f'regular users cannot edit this expression {x}')\n\n\ndef c(x):\n    raise RuntimeError('a bad day for regular maintenance of the expression cache')\n")
for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
    subprocess.run(["git", *c], cwd=R, capture_output=True)
def cli(*a):
    return subprocess.run([PY, "-m", "devkb.cli", *a, "--project", str(R)], cwd=W, env={**__import__("os").environ, "PYTHONPATH": str(W)}, capture_output=True, text=True, timeout=300).stdout
cli("build")
def listed(text):
    out = cli("pack", "error", text)
    sec = out.split("## Raised by", 1)[-1].split("\n## ", 1)[0] if "## Raised by" in out else ""
    return [l.split("`")[1] for l in sec.splitlines() if l.startswith("- `")], out
got, _ = listed("bad regular expression")
none, out = listed("regular expression cache layer warms slowly")
ok = {"raiser_listed_only": got == ["pkg/rx.py::compile_pattern"],
      "no_near_matches_for_unraised_text": none == [] and ("no function" in out.lower() or "does not" in out.lower() or "no error" in out.lower() or "not raise" in out.lower())}
print(json.dumps({"pass": all(ok.values()), **ok}))
