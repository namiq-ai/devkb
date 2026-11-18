"""#126 before/after: does the devkb-repo policy + guardrail change how an agent implements a devkb fix?

  python policybench.py run ISSUE[,ISSUE...] [--reps 2] [--parallel 2]
  python policybench.py score ISSUE[,ISSUE...]

before: origin/main as it is (no AGENTS.md/CLAUDE.md/.mcp.json, no graph), guardrail off. devkb is on PATH, as on
        this machine.
after:  the #126 branch (policy in AGENTS.md, CLAUDE.md import, .mcp.json lean-pack, .claude/settings.json guardrail),
        graphs built for the checkout and the corpus, guardrail on.
Both: the C/C++ corpus copied in with its .git, the issue as filed, Sonnet, same caps. Scored by accept/<issue>.py.
"""
import concurrent.futures as cf
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import storybench as sb

B = sb.B
BASES = {"before": "origin/main", "after": "ce284c4", "after2": os.environ.get("POLICY_BRANCH", "chore/126-devkb-first-on-devkb"),
         "cli": os.environ.get("POLICY_BRANCH", "chore/126-devkb-first-on-devkb")}   # after2 without the MCP server
# after2 (the revised #126 + #127): navigation through the branch's own devkb, which records every query
TOOL = {"after2": str(B / "toolenv-126" / "bin" / "devkb"), "cli": str(B / "toolenv-126" / "bin" / "devkb")}
PROMPT = """You are working in a clone of devkb (a code-graph tool for coding agents; Python; its venv is .venv, run
Python as .venv/bin/python). The pinned C/C++ corpus repositories are in ./corpus/ (cJSON, leveldb, fmt), each its own
git repository. Fix the issue below: change the code, add a regression test that fails before your fix and passes
after it, keep the whole test suite passing (.venv/bin/python -m pytest -q), and commit your work with git. Do not
push and do not use gh.

# {title}

{body}
"""


def checkout(w: Path, arm: str):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(sb.REPO), "archive", BASES[arm]], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(w)], input=tar, check=True)
    for r in sb.CORPUS_REPOS:
        shutil.copytree(sb.CORPUS / r, w / "corpus" / r, ignore=shutil.ignore_patterns(".devkb"), symlinks=True)
    gi = w / ".gitignore"
    gi.write_text(gi.read_text() + "\ncorpus/\n")
    sb.sh(["git", "init", "-q"], cwd=w)
    for c in (["add", "-A"], ["-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", f"devkb ({arm})"]):
        sb.sh(["git", *c], cwd=w)
    sb.sh(["uv", "venv", "-q", ".venv"], cwd=w)
    sb.sh(["uv", "pip", "install", "-q", "--python", ".venv/bin/python", "-e", ".[dev]"], cwd=w)
    if arm != "before":                              # what a session in a #126 checkout has: graphs for repo and corpus
        for p in [w, *(w / "corpus" / r for r in sb.CORPUS_REPOS)]:
            subprocess.run([TOOL.get(arm, sb.DEVKB), "build", "--project", str(p)], capture_output=True)
        sb.check_graphs(w)
    (w / ".bench-base").write_text(sb.sh(["git", "rev-parse", "HEAD"], cwd=w).stdout.strip())


def run_one(issue: str, arm: str, rep: int) -> str:
    tag = f"p{issue}-{arm}-r{rep}"
    out = B / "runs" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = B / "work" / tag
    checkout(w, arm)
    t = json.loads(sb.sh(["gh", "issue", "view", issue, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
    if arm.startswith("after"):                      # "cli": no MCP server, devkb only through the shell
        mcp = str(w / ".mcp.json")
        cfg = json.loads(Path(mcp).read_text())
        cfg["mcpServers"]["devkb"]["command"] = TOOL.get(arm, sb.DEVKB)
        Path(mcp).write_text(json.dumps(cfg, indent=2) + "\n")
    else:
        mcp = str(B / "no-mcp.json")
        Path(mcp).write_text(json.dumps({"mcpServers": {}}))
    cmd = ["claude", "-p", PROMPT.format(title=t["title"], body=t["body"]), "--model", sb.MODEL, "--output-format",
           "stream-json", "--verbose", "--max-turns", "150", "--permission-mode", "acceptEdits", "--strict-mcp-config",
           "--mcp-config", mcp, "--allowedTools", *sb.ALLOW, "--disallowedTools", *sb.DENY]
    env = dict(os.environ, DEVKB_GUARDRAIL="0" if arm == "before" else "1",
               PATH=f"{Path(TOOL.get(arm, sb.DEVKB)).parent}:{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    t0 = time.time()
    with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
        try:
            code = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=2700).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0)}))
    return f"done {tag} exit={code} {round(time.time() - t0)}s"


def score(issues):
    rows = []
    for issue in issues:
        for out in sorted((B / "runs").glob(f"p{issue}-*")):
            _, arm, rep = out.name.split("-")
            w = B / "work" / out.name
            end = json.loads((out / "end").read_text())
            base = (w / ".bench-base").read_text().strip()
            t = subprocess.run([str(w / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=w,
                               capture_output=True, text=True, timeout=1800)
            a = subprocess.run([sys.executable, str(B / "accept" / f"{issue}.py"), str(w)], capture_output=True,
                               text=True, timeout=1800)
            logs = [p for p in w.rglob("*.jsonl") if ".venv" not in p.parts and "corpus" not in p.parts
                    and ".devkb" not in p.parts and p.stat().st_mtime > float(end.get("start", 0) or 0)
                    and '"verdict"' in p.read_text(errors="replace")[:4000]]
            changed = sb.sh(["git", "diff", "--name-only", base], cwd=w).stdout.split()
            rows.append({"run": out.name, "issue": issue, "arm": arm, "rep": rep, "exit": end["exit"],
                         "seconds": end["seconds"], "suite_pass": t.returncode == 0,
                         "suite": (t.stdout.strip().splitlines() or [""])[-1],
                         "acceptance": json.loads(a.stdout.strip().splitlines()[-1]) if a.stdout.strip() else {"error": a.stderr[-300:]},
                         "dogfood_log": [str(p.relative_to(w)) for p in logs if str(p.relative_to(w)) in changed or
                                         sb.sh(["git", "status", "--porcelain", str(p.relative_to(w))], cwd=w).stdout],
                         "diff": sb.sh(["git", "diff", "--shortstat", base], cwd=w).stdout.strip(),
                         "telemetry": sum(len((d / ".devkb" / "process-api-telemetry.jsonl").read_text().splitlines())
                                          for d in [w, *(w / "corpus" / r for r in sb.CORPUS_REPOS)]
                                          if (d / ".devkb" / "process-api-telemetry.jsonl").exists()),
                         **sb.transcript(out / "stream.jsonl")})
            r = rows[-1]
            print(r["run"], "pass" if r["acceptance"].get("pass") else "FAIL", "suite" if r["suite_pass"] else "SUITE-RED",
                  f"${r['cost']:.2f}", "devkb", r["devkb_queries"], "guard", r["guardrail_fired"], "log", r["dogfood_log"], flush=True)
    with open(B / "results-policy.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    issues = a[1].split(",")
    if a[0] == "run":
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 2
        par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 2
        arms = os.environ.get("POLICY_ARMS", "before,after").split(",")
        jobs = [(i, arm, r) for i in issues for arm in arms for r in range(1, reps + 1)]
        random.Random(126).shuffle(jobs)
        with cf.ThreadPoolExecutor(par) as ex:
            for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
                print(f.result(), flush=True)
    else:
        score(issues)
