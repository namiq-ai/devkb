"""SPEC-DKB-004 §6: each story implemented by headless agents, devkb against devkb + guardrail.

  python storybench.py run ISSUE [--reps 2] [--parallel 2]
  python storybench.py score ISSUE

Each run: a fresh repository holding devkb `main` as one commit (no history), its own venv with devkb's dev extras
and libclang, the C/C++ corpus copied in (cJSON, leveldb, fmt at their pins), `devkb init --toolset lean-pack` from
the released devkb (graph built at setup). The prompt is the GitHub issue as filed. Arms differ only in
DEVKB_GUARDRAIL (0 / 1) for the user-level pre-search hook (~/.claude/hooks/devkb-guardrail.py).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

B = Path(__file__).resolve().parent
REPO = Path(os.environ.get("STORYBENCH_REPO", str(Path(__file__).resolve().parents[2])))   # the devkb checkout
BASE = os.environ.get("STORYBENCH_BASE", "origin/main")
CORPUS = Path.home() / ".cache" / "devkb" / "cpp-corpus"
CORPUS_REPOS = ("cJSON", "leveldb", "fmt")
DEVKB = os.environ.get("STORYBENCH_DEVKB", str(Path.home() / ".local" / "bin" / "devkb"))
GUARD_LOG = Path.home() / ".claude" / "hooks" / "devkb-guardrail.log"
ARMS = ("devkb", "guardrail")
MODEL = "sonnet"
PROMPT = """You are working in a clone of devkb (a code-graph tool for coding agents; Python; its venv is .venv, run
Python as .venv/bin/python; libclang is installed in it). The pinned C/C++ corpus repositories are in ./corpus/
(cJSON, leveldb, fmt). The specification this story belongs to is docs/specs/SPEC-DKB-004_cpp-supported.md (in this
checkout). Implement the story below completely: code, fixture tests, and any measurement or document it asks for.
Keep the whole test suite passing (.venv/bin/python -m pytest -q). Commit your work with git when done. Do not push
and do not use gh.

# {title}

{body}
"""
ALLOW = ["Read", "Edit", "Write", "Glob", "Grep", "TodoWrite", "mcp__devkb",
         "Bash(git:*)", "Bash(.venv/bin/python:*)", "Bash(.venv/bin/pytest:*)", "Bash(python3:*)", "Bash(devkb:*)",
         "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(grep:*)",
         "Bash(rg:*)", "Bash(diff:*)", "Bash(sed -n:*)", "Bash(awk:*)", "Bash(sort:*)", "Bash(uniq:*)", "Bash(mkdir:*)",
         "Bash(make:*)", "Bash(cd:*)", "Bash(echo:*)", "Bash(jq:*)"]
DENY = ["Bash(git push:*)", "Bash(gh:*)", "Task", "WebFetch", "WebSearch"]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def spec_file() -> Path:
    """The spec travels with the checkout even before its PR is merged."""
    return REPO / "docs" / "specs" / "SPEC-DKB-004_cpp-supported.md"


def check_graphs(w: Path):
    """Refuse a checkout whose corpus graphs are empty (2026-11-17: corpus copied without .git gave 3-node graphs)."""
    for r in CORPUS_REPOS:
        m = json.loads((w / "corpus" / r / ".devkb" / "manifest.json").read_text())
        if m.get("node_count", 0) < 500:
            raise SystemExit(f"corpus graph for {r} has {m.get('node_count')} nodes: checkout is broken")


def checkout(w: Path):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(REPO), "archive", BASE], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(w)], input=tar, check=True)
    for f in ("docs/specs/SPEC-DKB-004_cpp-supported.md", "docs/specs/cpp-supported-dogfood.jsonl", "bench/cpp/split_wrong.py"):
        src = REPO / f
        if src.exists() and not (w / f).exists():
            (w / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, w / f)
    for r in CORPUS_REPOS:
        shutil.copytree(CORPUS / r, w / "corpus" / r, ignore=shutil.ignore_patterns(".devkb"), symlinks=True)   # keep .git: devkb uses and the truth list files through git
    (w / ".gitignore").write_text((w / ".gitignore").read_text() + "\ncorpus/\n" if (w / ".gitignore").exists() else "corpus/\n")
    sh(["git", "init", "-q"], cwd=w)
    for c in (["add", "-A"], ["-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "devkb main + SPEC-DKB-004"]):
        sh(["git", *c], cwd=w)
    sh(["uv", "venv", "-q", ".venv"], cwd=w)
    sh(["uv", "pip", "install", "-q", "--python", ".venv/bin/python", "-e", ".[dev]", "libclang"], cwd=w)
    sh([DEVKB, "init", "--project", str(w), "--toolset", "lean-pack"], cwd=w)
    cfg = json.loads((w / ".mcp.json").read_text())
    cfg["mcpServers"]["devkb"]["command"] = DEVKB
    (w / ".mcp.json").write_text(json.dumps(cfg, indent=2) + "\n")
    for r in CORPUS_REPOS:                         # graphs for the corpus too, so devkb can answer about it
        subprocess.run([DEVKB, "build", "--project", str(w / "corpus" / r)], capture_output=True)
    check_graphs(w)
    sh(["git", "add", "-A"], cwd=w)
    sh(["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "devkb init"], cwd=w)
    (w / ".bench-base").write_text(sh(["git", "rev-parse", "HEAD"], cwd=w).stdout.strip())


def run_one(issue: str, arm: str, rep: int) -> str:
    tag = f"{issue}-{arm}-r{rep}"
    out = B / "runs" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = B / "work" / tag
    checkout(w)
    t = json.loads(sh(["gh", "issue", "view", issue, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
    cmd = ["claude", "-p", PROMPT.format(title=t["title"], body=t["body"]), "--model", MODEL, "--output-format",
           "stream-json", "--verbose", "--max-turns", "250", "--permission-mode", "acceptEdits", "--strict-mcp-config",
           "--mcp-config", str(w / ".mcp.json"), "--allowedTools", *ALLOW, "--disallowedTools", *DENY]
    env = dict(os.environ, DEVKB_GUARDRAIL="1" if arm == "guardrail" else "0",
               PATH=f"{Path(DEVKB).parent}:{w / '.venv' / 'bin'}:{os.environ['PATH']}")
    t0 = time.time()
    with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
        try:
            code = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=5400).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0)}))
    return f"done {tag} exit={code} {round(time.time() - t0)}s"


def run(issue: str, reps: int, parallel: int):
    jobs = [(issue, a, r) for a in ARMS for r in range(1, reps + 1)]
    random.Random(int(issue)).shuffle(jobs)
    with cf.ThreadPoolExecutor(parallel) as ex:
        for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
            print(f.result(), flush=True)


_DEVKB_CMD = re.compile(r"(\S*/)?(devkb|python\S*\s+(?:-P\s+)?-m\s+devkb[\w.]*)\s+(symbol|uses|outline|pack|docs|misses|tests|config|flows|review)\b")


def edits_devkb_code(file_path: str, root: str | None = None) -> bool:
    """Whether an edit changes devkb's own code, judged on the path inside the checkout (#302). A checkout that sits under
    a folder named `devkb` must not make every edit one, and an absolute path outside the checkout is not its code.
    Without a root (a transcript with no init event) an absolute path is judged as before: `devkb/` or `scripts/` anywhere."""
    fp = file_path or ""
    if root:
        r = root.rstrip("/") + "/"
        if fp.startswith(r):
            fp = fp[len(r):]
        elif fp.startswith("/"):
            return False
        return bool(re.match(r"(\./)?(devkb|scripts)/", fp))
    return bool(re.search(r"(^|/)(devkb|scripts)/", fp))


def devkb_commands(command: str, edited: bool = False) -> tuple[int, int]:
    """(navigation queries, self-tests) among the devkb commands in one shell command (#258). The repository the agents
    edit is devkb itself, so a devkb command after the run has edited devkb's code tests the change, and so does a
    query against a fixture outside the checkout (`--project /tmp/…`). Before the first such edit, a query is
    navigation, whichever devkb runs it (the checkout's .venv included: D1 teaches that command)."""
    nav = own = 0
    c = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "", command or "", flags=re.S)   # heredoc bodies are text
    c = re.sub(r"--project([ =])(['\"])([^'\"]*)\2", r"--project\1\3", c)    # a quoted fixture path is the same path (#302)
    c = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", c)                     # quoted strings are text
    for seg in re.split(r"&&|\|\||;|\||\n", c):
        seg = re.sub(r"^\s*(?:cd\s+\S+\s*|[A-Z_]+=\S+\s+)*", "", seg)
        if not _DEVKB_CMD.match(seg):
            continue
        p = re.search(r"--project[ =](\S+)", seg)
        if edited or (p and p.group(1).startswith(("/tmp", "/var/folders"))):
            own += 1
        else:
            nav += 1
    return nav, own


def transcript(path: Path) -> dict:
    sys.path.insert(0, str(REPO / "bench" / "audit"))
    from toolmix import classify, devkb_queries, size  # noqa: PLC0415
    kinds, calls, chars, msgs = {}, Counter(), Counter(), set()
    res, session, dq, nav, own, outs, edited, root = {}, None, 0, 0, 0, {}, False, None
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            session, root = e.get("session_id"), e.get("cwd") or root
        if e.get("type") == "result":
            res = e
        m = e.get("message")
        if not isinstance(m, dict):
            continue
        if e.get("type") == "assistant" and m.get("id"):
            msgs.add(m["id"])
            outs[m["id"]] = max(outs.get(m["id"], 0), (m.get("usage") or {}).get("output_tokens", 0))
        for x in m.get("content") or []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use":
                k = "devkb" if x["name"].startswith("mcp__devkb") else classify(x["name"], x.get("input", {}))
                kinds[x["id"]] = k
                calls[k] += 1
                dq += 1 if x["name"].startswith("mcp__devkb") else devkb_queries(x.get("input", {}).get("command", ""))
                if x["name"].startswith("mcp__devkb"):
                    nav += 1
                elif x["name"] == "Bash":
                    n, o = devkb_commands(x.get("input", {}).get("command", ""), edited)
                    nav, own = nav + n, own + o
                fp = str(x.get("input", {}).get("file_path", ""))
                if x["name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit") and edits_devkb_code(fp, root):
                    edited = True                     # from here on, a devkb command tests the change
            elif x.get("type") == "tool_result" and x.get("tool_use_id") in kinds:
                chars[kinds[x["tool_use_id"]]] += size(x.get("content", ""))
    u = res.get("usage") or {}
    ctx = sum(u.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    for mu in (res.get("modelUsage") or {}).values():    # cumulative per model, when present
        ctx = max(ctx, sum(mu.get(k, 0) for k in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")))
    out = sum(mu.get("outputTokens", 0) for mu in (res.get("modelUsage") or {}).values()) or sum(outs.values())
    fired, actions = guardrail_actions(session)
    # turns: the result's num_turns counts only the last turn of a session (#258); each assistant message is one
    # model call. out_tokens: modelUsage holds the session's totals; per-message usage in the stream is partial.
    return {"session": session, "turns": len(msgs), "cost": res.get("total_cost_usd", 0),
            "model_calls": len(msgs), "ctx_tokens": ctx, "out_tokens": out,
            "devkb_queries": dq, "devkb_nav": nav, "devkb_selftest": own, "calls": dict(calls), "chars": dict(chars), "guardrail_fired": fired,
            "guardrail_actions": actions}


def guardrail_actions(session: str, log: Path | None = None) -> tuple[int, dict]:
    """(decisions that reached the agent, every decision by action) for one session (#209). A pass-through sends the
    agent nothing, so it is not a firing."""
    log = log or GUARD_LOG
    acts: dict = {}
    if session and log.exists():
        for line in open(log, errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("session") == session:
                a = r.get("action") or "remind"          # the oldest lines had no action: a reminder
                acts[a] = acts.get(a, 0) + 1
    return sum(n for a, n in acts.items() if a != "pass-through"), acts


def score(issue: str):
    rows = []
    for out in sorted((B / "runs").glob(f"{issue}-*")):
        _, arm, rep = out.name.split("-")
        w = B / "work" / out.name
        end = json.loads((out / "end").read_text())
        base = (w / ".bench-base").read_text().strip()
        t = subprocess.run([str(w / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"], cwd=w,
                           capture_output=True, text=True, timeout=1800)
        acc = B / "accept" / f"{issue}.py"                       # story-specific acceptance, if written
        a = subprocess.run([str(w / ".venv/bin/python"), str(acc), str(w)], capture_output=True, text=True,
                           timeout=3600) if acc.exists() else None
        rows.append({"run": out.name, "arm": arm, "rep": rep, "exit": end["exit"], "seconds": end["seconds"],
                     "suite_pass": t.returncode == 0, "suite": (t.stdout.strip().splitlines() or [""])[-1],
                     "acceptance": json.loads(a.stdout.strip().splitlines()[-1]) if a and a.stdout.strip() else None,
                     "commits": int(sh(["git", "rev-list", "--count", f"{base}..HEAD"], cwd=w).stdout.strip() or 0),
                     "diff": sh(["git", "diff", "--shortstat", base], cwd=w).stdout.strip(),
                     **transcript(out / "stream.jsonl")})
        print(json.dumps({k: rows[-1][k] for k in ("run", "suite_pass", "cost", "turns", "devkb_queries", "guardrail_fired")}), flush=True)
    with open(B / f"results-{issue}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "run":
        run(a[1], int(a[a.index("--reps") + 1]) if "--reps" in a else 2, int(a[a.index("--parallel") + 1]) if "--parallel" in a else 2)
    else:
        score(a[1])
