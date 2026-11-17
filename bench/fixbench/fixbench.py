"""Bug fixing with devkb against plain: the same tickets, fixed by fresh headless agents in isolated checkouts.

  python fixbench.py setup                         fetch the ticket texts
  python fixbench.py run [--reps 2] [--parallel 4]  run every (ticket, arm, rep) not yet run, in random order
  python fixbench.py score                          hidden acceptance tests + full suite + transcript metrics -> results.jsonl

Each run: a fresh repository holding only main at 4369145 as one commit (no history, no fix branches), its own venv.
`devkb` arm: `devkb init --toolset lean-pack` from the installed release (AGENTS.md block, CLAUDE.md import, .mcp.json,
graph), committed as part of the setup. `plain` arm: none of it; `devkb` commands are denied. Same model, prompt, tools,
turn and time caps. Acceptance: the fix commit's own tests (hidden, loosened to behaviour), copied in after the run.
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
from pathlib import Path

B = Path(__file__).resolve().parent
REPO = os.environ.get("FIXBENCH_REPO", str(B.parent.parent))   # the devkb checkout holding BASE
BASE = "4369145"
TICKETS = [50, 54, 70, 57, 63, 65]
VARIANT = os.environ.get("FIXBENCH_VARIANT", "")      # "" = tickets as filed, released 0.2.7; "B" = no "where to start", main's devkb
SUF = f"-{VARIANT}" if VARIANT else ""
TICKETS = [int(x) for x in os.environ.get("FIXBENCH_TICKETS", "").split(",") if x] or TICKETS
# Variant B's tool: `uv venv toolenv && uv pip install --python toolenv/bin/python "<checkout of BASE>[mcp]"`, and
# shim-B/devkb -> toolenv/bin/devkb; the other variants' shim/devkb -> the installed release.
DEVKB = os.environ.get("FIXBENCH_DEVKB") or (str(B / "toolenv" / "bin" / "devkb") if VARIANT == "B" else os.path.expanduser("~/.local/bin/devkb"))
MODEL = "sonnet"
PROMPT = """You are working in a clone of the devkb repository (a Python code-graph tool for coding agents; its venv is
.venv, run Python as .venv/bin/python). Fix the GitHub issue below. Add a regression test under tests/ that fails
before your fix and passes after it, make sure the whole suite passes (.venv/bin/python -m pytest -q tests), then
commit your change with git. Do not push and do not use gh.

# #{n}: {title}

{body}
"""
COMMON = ["Read", "Edit", "Write", "Glob", "Grep", "TodoWrite",
          "Bash(git:*)", "Bash(.venv/bin/python:*)", "Bash(python3:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)",
          "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(diff:*)", "Bash(sed -n:*)", "Bash(mkdir:*)"]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def setup():
    (B / "tickets").mkdir(exist_ok=True)
    for n in TICKETS:
        d = json.loads(sh(["gh", "issue", "view", str(n), "--repo", "namiq-ai/devkb", "--json", "title,body"]).stdout)
        (B / "tickets" / f"{n}.json").write_text(json.dumps(d))
    print("tickets:", TICKETS)


def checkout(w: Path, arm: str):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", REPO, "archive", BASE], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(w)], input=tar, check=True)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "main"]):
        sh(["git", *c], cwd=w)
    sh(["uv", "venv", "-q", ".venv"], cwd=w)
    sh(["uv", "pip", "install", "-q", "--python", ".venv/bin/python", "-e", ".[mcp]", "pytest"], cwd=w)
    if arm in ("devkb", "hook"):
        sh([DEVKB, "init", "--project", str(w), "--toolset", "lean-pack", *(["--claude-hook"] if arm == "hook" else [])], cwd=w)
        if arm == "hook":   # the hook runs the released tool too, never the code being edited
            st = json.loads((w / ".claude" / "settings.json").read_text())
            for h in st["hooks"]["PreToolUse"][0]["hooks"]:
                h["command"] = h["command"].replace("devkb ", DEVKB + " ", 1)
            (w / ".claude" / "settings.json").write_text(json.dumps(st, indent=2) + "\n")
        # the server and the `devkb` command are the released tool, never the code the agent is editing
        cfg = json.loads((w / ".mcp.json").read_text())
        cfg["mcpServers"]["devkb"]["command"] = DEVKB
        (w / ".mcp.json").write_text(json.dumps(cfg, indent=2) + "\n")
        sh(["git", "add", "-A"], cwd=w)
        sh(["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "devkb init"], cwd=w)
    (w / ".bench-base").write_text(sh(["git", "rev-parse", "HEAD"], cwd=w).stdout.strip())


def run_one(n: int, arm: str, rep: int) -> str:
    tag = f"{arm}-{n}-r{rep}"
    out = B / f"runs{SUF}" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = B / f"work{SUF}" / tag
    checkout(w, arm)
    t = json.loads((B / f"tickets{SUF}" / f"{n}.json").read_text())
    prompt = PROMPT.format(n=n, title=t["title"], body=t["body"])
    if arm in ("devkb", "hook"):
        mcp, allow, deny = str(w / ".mcp.json"), COMMON + ["mcp__devkb", "Bash(devkb:*)"], []
    else:
        (B / "no-mcp.json").write_text(json.dumps({"mcpServers": {}}))
        mcp, allow, deny = str(B / "no-mcp.json"), COMMON, ["Bash(devkb:*)"]
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose", "--max-turns", "150",
           "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", mcp, "--allowedTools", *allow,
           "--disallowedTools", "Bash(git push:*)", "Task", "WebFetch", "WebSearch", *deny]
    env = dict(os.environ, PATH=f"{B / ('shim' + SUF)}:{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    t0 = time.time()
    with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
        try:
            p = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=2700)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0)}))
    return f"done {tag} exit={code} {round(time.time() - t0)}s"


def run(reps: int, parallel: int):
    arms = os.environ.get("FIXBENCH_ARMS", "plain,devkb").split(",")
    jobs = [(n, arm, r) for n in TICKETS for arm in arms for r in range(1, reps + 1)]
    random.Random(2032).shuffle(jobs)
    with cf.ThreadPoolExecutor(parallel) as ex:
        for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
            print(f.result(), flush=True)


def score():
    sys.path.insert(0, str(B.parent / "audit"))
    from toolmix import classify, devkb_queries, size   # the audit's transcript classifier (bench/audit/toolmix.py)
    meta = json.loads((B / "hidden" / "meta.json").read_text())
    rows = []
    for out in sorted((B / f"runs{SUF}").iterdir()):
        arm, n, rep = out.name.split("-")
        w = B / f"work{SUF}" / out.name
        end = json.loads((out / "end").read_text())
        hidden = B / "hidden" / f"test_hidden_{n}.py"
        shutil.copy(hidden, w / "tests" / hidden.name)
        if (B / "hidden" / "_t3common.py").exists():
            shutil.copy(B / "hidden" / "_t3common.py", w / "tests" / "_t3common.py")
        py = str(w / ".venv" / "bin" / "python")
        h = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tests/{hidden.name}"], cwd=w,
                           capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(w)))
        full = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", "--ignore", f"tests/{hidden.name}"],
                              cwd=w, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(w)))
        (w / "tests" / hidden.name).unlink()
        (w / "tests" / "_t3common.py").unlink(missing_ok=True)
        base = (w / ".bench-base").read_text().strip()
        diff = sh(["git", "diff", "--shortstat", base], cwd=w).stdout.strip()
        committed = sh(["git", "rev-list", "--count", f"{base}..HEAD"], cwd=w).stdout.strip()
        cost = turns = 0
        kinds, dq = {}, 0
        from collections import Counter
        calls, chars = Counter(), Counter()
        for line in open(out / "stream.jsonl"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                cost, turns = e.get("total_cost_usd", 0), e.get("num_turns", 0)
            m = e.get("message"); content = m.get("content") if isinstance(m, dict) else None
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
        rows.append({"run": out.name, "arm": arm, "ticket": int(n), "rep": rep, "exit": end["exit"], "seconds": end["seconds"],
                     "hidden_pass": h.returncode == 0, "hidden": h.stdout.strip().splitlines()[-1] if h.stdout.strip() else "",
                     "suite_pass": full.returncode == 0, "suite": full.stdout.strip().splitlines()[-1] if full.stdout.strip() else "",
                     "commits": int(committed), "diff": diff, "cost": cost, "turns": turns, "devkb_queries": dq,
                     "calls": dict(calls), "chars": dict(chars)})
        print(rows[-1]["run"], rows[-1]["hidden_pass"], rows[-1]["suite_pass"], round(cost, 3), turns, dq, flush=True)
    with open(B / f"results{SUF}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "setup":
        setup()
    elif a[0] == "run":
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 2
        par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 4
        run(reps, par)
    elif a[0] == "score":
        score()
