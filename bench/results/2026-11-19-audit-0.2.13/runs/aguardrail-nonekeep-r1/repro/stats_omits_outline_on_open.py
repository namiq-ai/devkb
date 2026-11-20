"""#188 / SPEC-DKB-007 R7: `devkb guardrail-stats` counts every action. The D2 `outline-on-open` decision is logged but is
in neither the per-action line nor the intent table."""
import subprocess, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, PY, ROOT, _env

src = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(45))
repo = fixture({"big.py": src})
kind, text = hook(repo, "Read", {"file_path": str(repo / "big.py")}, env_extra={"DEVKB_GUARDRAIL_OUTLINE": "1"})
print("Read of a 180-line file: hook", kind, "|", text.splitlines()[0] if text else "")
log = repo.parent / "home" / ".claude" / "hooks" / "devkb-guardrail.log"
print("log:", log.read_text().strip())
out = subprocess.run([str(PY), "-P", "-m", "devkb.cli", "guardrail-stats", "--log", str(log)], cwd=repo,
                     env=_env(repo.parent / "home"), capture_output=True, text=True).stdout
print(out)
if "outline-on-open" not in out:
    print("DEFECT: a logged outline-on-open decision is counted nowhere in guardrail-stats")
    sys.exit(1)
print("ok")
