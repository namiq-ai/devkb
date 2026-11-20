"""#369: benchmark agents' commands are not refused for their form. Each denial form has a recorded cause and fix in
docs/BENCHMARK.md; the allow rules and the prompt line are the same in every arm (a test asserts it); the prompt tells
agents how to run commands so the settings do not refuse them.
Black box on the checkout's files and the prompt the bench builds. Prints one JSON line."""
import json, re, subprocess, sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
doc = (W / "docs" / "BENCHMARK.md").read_text(errors="replace") if (W / "docs" / "BENCHMARK.md").exists() else ""
sec = doc[doc.lower().find("denial"):] if "denial" in doc.lower() else ""
forms = {"cd": r"`cd\b", "heredoc": r"(?i)heredoc|<<", "redirect or variable": r"(?i)redirect|variable|\$\(|`>`",
         "venv by absolute path": r"(?i)absolute.{0,40}venv|venv.{0,40}absolute"}
res["forms_recorded"] = bool(sec) and all(re.search(p, sec) for p in forms.values())
res["probe_recorded"] = bool(re.search(r"(?i)claude -p|headless", sec))
tests = [p for p in (W / "tests").glob("test_*.py") if re.search(r"ALLOW", p.read_text(errors="replace"))
         and re.search(r"(?i)every arm|all arms|for a(rm)? in|arms", p.read_text(errors="replace"))]
res["same_rules_tested"] = bool(tests)
# the prompt the bench gives, for an arm without and an arm with devkb: identical, and it says how to run commands
code = ("import sys; sys.path.insert(0, 'bench/policy'); import policybench as pb\n"
        "a = pb.prompt_for('1', 'T', 'Body.', None); b = pb.prompt_for('2', 'T', 'Body.', None)\n"
        "print(a == b.replace('', '') and a)")
p = subprocess.run([sys.executable, "-c", code], cwd=W, capture_output=True, text=True)
prompt = p.stdout
res["prompt_says_how_to_run_commands"] = bool(re.search(r"(?i)(Edit|Write) tool", prompt)) and bool(
    re.search(r"(?i)checkout|repository root|working directory", prompt))
print(json.dumps({"results": res, "pass": all(res.values())}))
