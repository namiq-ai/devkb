"""T2: bug fixing in a large unfamiliar repository (sympy 1.13.3), plain against devkb against devkb + hook.

  python fixbench_sympy.py run [--reps 2] [--parallel 4]
  python fixbench_sympy.py score

Each run: a fresh repository holding sympy at its tag with one injected bug, as a single commit (no history), its own
venv. Tickets are in a user's words (bugs/<id>/ticket.json). Acceptance: sympy's own tests for the faulty code
(bugs/<id>/acceptance.txt), with those test files restored from the tag before they run, so editing them cannot pass.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

B = Path(__file__).resolve().parent
S = Path(os.environ.get("FIXBENCH_SYMPY", str(B / "sympy")))
SRC = S / "src"                                   # clean sympy at sympy-1.13.3, cloned per sympy/README.md (not committed)
BUGS = sorted(p.name for p in (S / "bugs").iterdir() if p.is_dir())
DEVKB = os.environ.get("FIXBENCH_DEVKB", os.path.expanduser("~/.local/bin/devkb"))   # 0.2.10 or later: sympy needs #104-#106
SHIM = B / "shim-E"
MODEL = "sonnet"
PROMPT = """You are working in a clone of sympy (a large Python library for symbolic mathematics; its venv is .venv, run
Python as .venv/bin/python). A user reported the bug below. Find its cause and fix it. Add a regression test that fails
before your fix and passes after it, run the tests relevant to your change (the whole suite is too long to run), then
commit your change with git. Do not push and do not use gh.

# {title}

{body}
"""
COMMON = ["Read", "Edit", "Write", "Glob", "Grep", "TodoWrite",
          "Bash(git:*)", "Bash(.venv/bin/python:*)", "Bash(python3:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)",
          "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(diff:*)", "Bash(sed -n:*)", "Bash(mkdir:*)"]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def checkout(w: Path, bug: str, arm: str):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(SRC), "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(w)], input=tar, check=True)
    sh(["git", "init", "-q"], cwd=w)
    sh(["git", "apply", str(S / "bugs" / bug / "mutation.patch")], cwd=w)
    for c in (["add", "-A"], ["-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "sympy 1.13.3"]):
        sh(["git", *c], cwd=w)
    sh(["uv", "venv", "-q", ".venv"], cwd=w)
    sh(["uv", "pip", "install", "-q", "--python", ".venv/bin/python", "-e", ".", "pytest", "mpmath", "hypothesis"], cwd=w)
    if arm in ("devkb", "hook"):
        sh([DEVKB, "init", "--project", str(w), "--toolset", "lean-pack", *(["--claude-hook"] if arm == "hook" else [])], cwd=w)
        cfg = json.loads((w / ".mcp.json").read_text())
        cfg["mcpServers"]["devkb"]["command"] = DEVKB
        (w / ".mcp.json").write_text(json.dumps(cfg, indent=2) + "\n")
        if arm == "hook":
            st = json.loads((w / ".claude" / "settings.json").read_text())
            for h in st["hooks"]["PreToolUse"][0]["hooks"]:
                h["command"] = h["command"].replace("devkb ", DEVKB + " ", 1)
            (w / ".claude" / "settings.json").write_text(json.dumps(st, indent=2) + "\n")
        sh(["git", "add", "-A"], cwd=w)
        sh(["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "devkb init"], cwd=w)
    (w / ".bench-base").write_text(sh(["git", "rev-parse", "HEAD"], cwd=w).stdout.strip())


def run_one(bug: str, arm: str, rep: int) -> str:
    tag = f"{arm}-{bug}-r{rep}"
    out = B / "runs-E" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = B / "work-E" / tag
    checkout(w, bug, arm)
    t = json.loads((S / "bugs" / bug / "ticket.json").read_text())
    prompt = PROMPT.format(title=t["title"], body=t["body"])
    if arm in ("devkb", "hook"):
        mcp, allow, deny = str(w / ".mcp.json"), COMMON + ["mcp__devkb", "Bash(devkb:*)"], []
    else:
        (B / "no-mcp.json").write_text(json.dumps({"mcpServers": {}}))
        mcp, allow, deny = str(B / "no-mcp.json"), COMMON, ["Bash(devkb:*)"]
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose", "--max-turns", "150",
           "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", mcp, "--allowedTools", *allow,
           "--disallowedTools", "Bash(git push:*)", "Task", "WebFetch", "WebSearch", *deny]
    env = dict(os.environ, PATH=f"{SHIM}:{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    t0 = time.time()
    with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
        try:
            code = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=2700).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0)}))
    return f"done {tag} exit={code} {round(time.time() - t0)}s"


def run(reps: int, parallel: int):
    arms = os.environ.get("FIXBENCH_ARMS", "plain,devkb,hook").split(",")
    jobs = [(b, a, r) for b in BUGS for a in arms for r in range(1, reps + 1)]
    random.Random(2032).shuffle(jobs)
    SHIM.mkdir(exist_ok=True)
    if not (SHIM / "devkb").exists():
        (SHIM / "devkb").symlink_to(DEVKB)
    with cf.ThreadPoolExecutor(parallel) as ex:
        for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
            print(f.result(), flush=True)


def score():
    sys.path.insert(0, str(B.parent / "audit"))   # bench/audit/toolmix.py
    from toolmix import classify, devkb_queries, size
    rows = []
    for out in sorted((B / "runs-E").iterdir()):
        arm, rest = out.name.split("-", 1)
        bug, rep = rest.rsplit("-", 1)
        w = B / "work-E" / out.name
        ids = (S / "bugs" / bug / "acceptance.txt").read_text().split()
        test_files = sorted({i.split("::")[0] for i in ids})
        for f in test_files:                      # the acceptance tests as shipped, whatever the agent did to them
            shutil.copy(SRC / f, w / f)
        py = str(w / ".venv" / "bin" / "python")
        h = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *ids], cwd=w, capture_output=True, text=True,
                           timeout=600)
        subprocess.run(["git", "checkout", "-q", "--", *test_files], cwd=w)
        base = (w / ".bench-base").read_text().strip()
        diff = sh(["git", "diff", "--shortstat", base], cwd=w).stdout.strip()
        fault = (S / "bugs" / bug / "mutation.patch").read_text().split("\n", 1)[0].split()[-1].removeprefix("b/")
        touched = sh(["git", "diff", "--name-only", base], cwd=w).stdout.split()
        cost = turns = dq = 0
        kinds, calls, chars = {}, Counter(), Counter()
        for line in open(out / "stream.jsonl"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                cost, turns = e.get("total_cost_usd", 0), e.get("num_turns", 0)
            m = e.get("message")
            content = m.get("content") if isinstance(m, dict) else None
            if not isinstance(content, list):
                continue
            for x in content:
                if x.get("type") == "tool_use":
                    k = "devkb" if x["name"].startswith("mcp__devkb") else classify(x["name"], x.get("input", {}))
                    kinds[x["id"]] = k
                    calls[k] += 1
                    dq += 1 if x["name"].startswith("mcp__devkb") else devkb_queries(x.get("input", {}).get("command", ""))
                elif x.get("type") == "tool_result" and x.get("tool_use_id") in kinds:
                    chars[kinds[x["tool_use_id"]]] += size(x.get("content", ""))
        end = json.loads((out / "end").read_text())
        rows.append({"run": out.name, "arm": arm, "bug": bug, "rep": rep, "exit": end["exit"], "seconds": end["seconds"],
                     "fixed": h.returncode == 0, "acceptance": h.stdout.strip().splitlines()[-1] if h.stdout.strip() else "",
                     "fault_file_touched": fault in touched, "diff": diff, "cost": cost, "turns": turns,
                     "devkb_queries": dq, "calls": dict(calls), "chars": dict(chars)})
        print(out.name, rows[-1]["fixed"], round(cost, 3), turns, dq, flush=True)
    with open(B / "results-E.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "run":
        run(int(a[a.index("--reps") + 1]) if "--reps" in a else 2, int(a[a.index("--parallel") + 1]) if "--parallel" in a else 4)
    else:
        score()
