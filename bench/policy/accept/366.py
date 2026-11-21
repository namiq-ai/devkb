"""#366: the benchmark measures what offering devkb costs a user's repository: a `userpolicy` arm whose checkout holds
exactly what `devkb init` writes, candidate arms, the first-call context of each in a committed note, and the rows.
Black box on the checkout's files: the bench defines the arm and builds its policy from `devkb init`'s block; a note in
docs/analysis gives first-call context for none, userpolicy and main; results rows with those arms are committed.
Prints one JSON line."""
import json, re, subprocess, sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
res = {}
pb = (W / "bench" / "policy" / "policybench.py").read_text(errors="replace")
res["userpolicy_arm_defined"] = bool(re.search(r"[\"']userpolicy[\"']\s*:", pb))
# the arm's AGENTS.md is what `devkb init` writes: the bench takes it from devkb's own init, not a copy of the text
# and it is the checkout's code that writes it, not a helper nothing calls
co = pb[pb.find("def checkout("):pb.find("\ndef ", pb.find("def checkout(") + 5)] if "def checkout(" in pb else ""
res["policy_from_devkb_init"] = bool(re.search(r"AGENTS_BLOCK|devkb\.init|\binit\b.*--agents|\[\"init\"", pb)) and \
    bool(re.search(r"userpolicy|USER_POLICY|user_policy|arm_files", co))
notes = [p for p in (W / "docs" / "analysis").glob("*.md")
         if "userpolicy" in (t := p.read_text(errors="replace")) and re.search(r"(?i)first[- ]call", t)]
text = "\n".join(p.read_text(errors="replace") for p in notes)
arms_in_bench = [a for a in re.findall(r"^\s*[\"'](\w+)[\"']:\s*[\"']origin/main[\"']", pb, re.M) if a in ("short", "outline", "inject", "userinit")]
res["note_gives_first_call_per_arm"] = bool(notes) and all(re.search(rf"\b{a}\b[^\n]*\d[\d.,]*\s*k", text)
                                                            for a in ("none", "userpolicy", "main", *arms_in_bench))
tracked = subprocess.run(["git", "-C", str(W), "ls-files"], capture_output=True, text=True).stdout.splitlines()
rows = [f for f in tracked if f.endswith(".jsonl") and ("results" in f or "rows" in f)]
has = False
for f in rows:
    try:
        arms = {json.loads(l).get("arm") for l in (W / f).read_text(errors="replace").splitlines() if l.strip().startswith("{")}
    except ValueError:
        continue
    has = has or ("userpolicy" in arms and ("none" in arms or "main" in arms))
res["rows_committed"] = has
print(json.dumps({"results": res, "pass": all(res.values())}))
