#!/usr/bin/env python3
"""Review a pull request two ways, with and without devkb, and compare the reviews (the per-ticket checklist's step 3, AGENTS.md).

The subject is PR #401 as it stood BEFORE its review fixes (head 65fba22), in a clean checkout whose history is two commits, the PR's
base and the PR, so `git diff HEAD~1 HEAD` is the PR and no later commit can leak a fix. Both arms get the same prompt and the same
read-only tools (no Edit/Write, no gh, no network); the devkb arm also has `devkb` on its PATH (this branch's origin/main commit) and a
graph of the PR's tree. AGENTS.md, CLAUDE.md and .claude/ are removed from both checkouts so neither inherits devkb instructions or hooks.

Quality: bench/review/pr401-known.json lists 15 defects in scope, each reproduced and fixed afterwards. A finding matches one when its
file and its words match; the findings that match none are adjudicated by hand into bench/review/pr401-adjudicated.json (real / false /
duplicate). Efficiency: turns, tokens, cost, wall time and calls, from the stream.

  review_bench.py run --arms nodevkb,devkb [--reps 3] [--parallel 3]
  review_bench.py score [--arms nodevkb,devkb]"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import re
import shutil
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import storybench as sb  # noqa: E402
import toolenv  # noqa: E402

BASE = subprocess.run(["git", "-C", str(ROOT), "merge-base", "origin/main", "65fba22"], capture_output=True, text=True).stdout.strip()
HEAD = "65fba22"
OUT = Path.home() / ".cache" / "devkb" / "review"
PY = os.environ.get("REVIEW_PY") or str(Path(sys.executable).parent)            # a python with pytest, pyyaml, mcp and NO devkb installed
SCOPE = "devkb/, scripts/, plugins/ and the benchmark harness code in bench/policy/*.py (including bench/policy/accept/*.py, which the PR can affect without editing them)"
PROMPT = """You are reviewing a GitHub pull request, checked out in the current directory. The PR is the last commit: `git diff HEAD~1 HEAD`.

The PR adds (a) `pack refactor` listing test files that call or quote a function with no call the graph resolved, and `pack file` marking tests direct or through a caller; (b) an opt-in prompt router and task-word recorder (`devkb hook prompt|context`, `devkb init --prompt-hook`) with a task-aware tie-break in `symbol`; (c) benchmark and replay tooling under bench/, including harness changes (`POLICY_BASES`, refuse-on-collision, `template_for(arm, issue)`, `checkout(w, arm, issue)`).

Review scope: {scope}. Ignore documentation and bench/quality.

Find real defects: wrong behaviour, regressions in existing behaviour or in code that depends on what changed, crashes on unusual input, resource or state problems, and tests that would pass for the wrong reason. Verify each claim by running something (a short python snippet, a test, a command) whenever you can; report only what you have reason to believe is real. No style nits and no restating the PR.

Finish with a JSON array in a ```json block, at most 15 objects, each {{"file": "...", "line": N, "severity": "blocker|should-fix|nit", "claim": "...", "evidence": "what you ran or read"}}."""
NOCLI = """

This repository is devkb itself. For this review do not use devkb's command line to look at the repository under review: no `devkb ...` and no `python -m devkb...` against this checkout or a copy of it. Reading the code with grep and Read, running its tests, and running the code under review against small fixtures that you create elsewhere to check a claim are all fine."""
DEVKB = """

`devkb` is on your PATH and the repository's graph is built. For a review it gives, for any changed file, the functions other files call, the files that depend on it and the tests that reach it: `devkb pack --project . file PATH`; for a function, its callers: `devkb pack --project . refactor NAME` (or `Class::method`); and `devkb symbol|outline|uses` to read code. Use it where it helps."""


def sh(cmd, cwd=None, timeout=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})}, input=input)


def tree(commit: str, dest: Path) -> None:
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", commit], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
    for n in (".claude", "AGENTS.md", "CLAUDE.md", ".mcp.json"):
        p = dest / n
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


def prepare(w: Path, env: dict | None) -> dict:
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    git = lambda *a: sh(["git", "-c", "user.name=r", "-c", "user.email=r@e.x", *a], cwd=w)
    git("init", "-q")
    tree(BASE, w)
    git("add", "-A")
    git("commit", "-qm", "base")
    git("rm", "-rq", "--cached", ".")
    for p in w.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    tree(HEAD, w)
    git("add", "-A")
    git("commit", "-qm", "the pull request")
    path = f"{PY}:{os.environ['PATH']}"
    if env:
        wrap = w.parent / (w.name + ".bin")
        wrap.mkdir(exist_ok=True)
        (wrap / "devkb").write_text(f'#!/bin/sh\nexec "{env["bin"]}" "$@"\n')
        (wrap / "devkb").chmod(0o755)
        sh([env["bin"], "build", "--project", str(w)], cwd=w, timeout=900)
        path = f"{wrap}:{path}"
    return {"PATH": path}


def run_one(arm: str, rep: int, env: dict | None) -> str:
    tag = f"{arm}-r{rep}"
    out = OUT / tag
    if (out / "score.json").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = OUT / "work" / tag
    t0 = time.time()
    e = prepare(w, env)
    (out / "no-mcp.json").write_text('{"mcpServers": {}}')
    deny = ["Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)", "Bash(wget:*)"] + ([] if env else ["Bash(devkb:*)"])
    if arm == "nocli":                                   # the checkout is devkb: `python -m devkb...` would be devkb navigation too
        deny += ["Bash(python -m devkb:*)", "Bash(python3 -m devkb:*)", "Bash(python -m devkb.cli:*)", "Bash(python3 -m devkb.cli:*)"]
    cmd = ["claude", "-p", "--model", sb.MODEL, "--setting-sources", "local", "--output-format", "stream-json", "--verbose", "--max-turns", "80",
           "--max-budget-usd", "8", "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", str(out / "no-mcp.json"),
           "--no-session-persistence", "--allowedTools", "Bash", "Read", "Grep", "Glob", "--disallowedTools", *deny]
    prompt = PROMPT.format(scope=SCOPE) + (DEVKB if env else NOCLI if arm == "nocli" else "")
    with open(out / "stream.jsonl", "w") as so, open(out / "stderr.log", "w") as se:
        p = subprocess.run(cmd, cwd=w, env={**os.environ, **e}, input=prompt, text=True, stdout=so, stderr=se, timeout=3000)
    ev = [json.loads(l) for l in open(out / "stream.jsonl") if l.startswith("{")]
    res = next((x for x in reversed(ev) if x.get("type") == "result"), {})
    row = {"run": tag, "arm": arm, "rep": rep, "exit": p.returncode, "seconds": round(time.time() - t0), "result": res.get("result") or "",
           "is_error": bool(res.get("is_error")), **sb.transcript(out / "stream.jsonl")}
    row.pop("hook_first_output", None)
    (out / "score.json").write_text(json.dumps(row))
    shutil.rmtree(w, ignore_errors=True)
    shutil.rmtree(w.parent / (w.name + ".bin"), ignore_errors=True)
    return f"done {tag} exit={p.returncode} turns={row['turns']} cost=${row['cost']} devkb={row['devkb_nav']} {row['seconds']}s"


def findings(text: str) -> list[dict]:
    m = list(re.finditer(r"```json\s*(.*?)```", text, re.S))
    if not m:
        return []
    try:
        d = json.loads(m[-1].group(1))
    except ValueError:
        return []
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def score(arms: list[str]) -> None:
    known = json.loads((HERE / "pr401-known.json").read_text())
    adj_file = HERE / "pr401-adjudicated.json"
    adj = json.loads(adj_file.read_text()) if adj_file.exists() else {}
    rows = [json.loads(f.read_text()) for f in sorted(OUT.glob("*/score.json"))]
    rows = [r for r in rows if r["arm"] in arms]
    per = {}
    unmatched = []
    for r in rows:
        fs, hit, rest = findings(r["result"]), set(), []
        for i, f in enumerate(fs):
            text = " ".join(str(f.get(k, "")) for k in ("file", "claim", "evidence")).lower()
            got = [g for g in known if re.search(g["file"], str(f.get("file", "")), re.I) and re.search(g["kw"], text, re.I)]
            if got:
                hit |= {g["id"] for g in got}
            else:
                rest.append((i, f))
        for i, f in rest:
            v = adj.get(f"{r['run']}#{i}")
            unmatched.append((r["run"], i, f, v))
        real = sum(1 for _r, _i, _f, v in unmatched if _r == r["run"] and v == "real")
        false = sum(1 for _r, _i, _f, v in unmatched if _r == r["run"] and v == "false")
        und = sum(1 for _r, _i, _f, v in unmatched if _r == r["run"] and v is None)
        per[r["run"]] = {"arm": r["arm"], "findings": len(fs), "known": sorted(hit), "new_real": real, "new_false": false, "undecided": und, "row": r}
    print(f"{len(rows)} reviews; {len(known)} known defects ({sum(1 for k in known if k['sev'] == 'blocker')} blocker)\n")
    print("| arm | reviews | known defects found (of 15) | blocker found | should-fix found (of 9) | nits found (of 5) | findings | new real | new false | undecided |\n|---|---|---|---|---|---|---|---|---|---|")
    sev = {k["id"]: k["sev"] for k in known}
    for a in arms:
        v = [x for x in per.values() if x["arm"] == a]
        if not v:
            continue
        m = lambda f: st.mean(f(x) for x in v)
        print(f"| {a} | {len(v)} | {m(lambda x: len(x['known'])):.1f} | {sum(1 for x in v if any(sev[k] == 'blocker' for k in x['known']))}/{len(v)} | "
              f"{m(lambda x: sum(1 for k in x['known'] if sev[k] == 'should-fix')):.1f} | {m(lambda x: sum(1 for k in x['known'] if sev[k] == 'nit')):.1f} | "
              f"{m(lambda x: x['findings']):.1f} | {m(lambda x: x['new_real']):.1f} | {m(lambda x: x['new_false']):.1f} | {m(lambda x: x['undecided']):.1f} |")
    print("\nReviews that navigated with devkb (a devkb command on the PR checkout or a copy of it, counted by the stream): " + ", ".join(
        f"{a} {sum(1 for x in per.values() if x['arm'] == a and x['row']['devkb_nav'])}/{sum(1 for x in per.values() if x['arm'] == a)}" for a in arms))
    print("\n| arm | turns | cost $ | context k tokens | output k tokens | wall min | search | read | run | devkb calls | cost per known defect $ |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for a in arms:
        v = [x for x in per.values() if x["arm"] == a]
        if not v:
            continue
        r = [x["row"] for x in v]
        c = lambda x, k: (x.get("calls") or {}).get(k, 0)
        known_n = st.mean(len(x["known"]) for x in v)
        print(f"| {a} | {st.mean(x['turns'] for x in r):.1f} | {st.mean(x['cost'] for x in r):.2f} | {st.mean(x['ctx_tokens'] for x in r) / 1e3:.0f} | {st.mean(x.get('out_tokens', 0) for x in r) / 1e3:.1f} | "
              f"{st.mean(x['seconds'] for x in r) / 60:.1f} | {st.mean(c(x, 'search') for x in r):.1f} | {st.mean(c(x, 'read') for x in r):.1f} | {st.mean(c(x, 'run') for x in r):.1f} | "
              f"{st.mean(x['devkb_nav'] for x in r):.1f} | {(st.mean(x['cost'] for x in r) / known_n) if known_n else float('nan'):.2f} |")
    print("\nper known defect, reviews that found it:")
    for g in known:
        print(f"  {g['id']} {g['sev']:10} " + "  ".join(f"{a} {sum(1 for x in per.values() if x['arm'] == a and g['id'] in x['known'])}/{sum(1 for x in per.values() if x['arm'] == a)}" for a in arms) + f"   {g['what'][:70]}")
    todo = [(r, i, f) for r, i, f, v in unmatched if v is None]
    if todo:
        (HERE / "pr401-unmatched.json").write_text(json.dumps([{"key": f"{r}#{i}", **f} for r, i, f in todo], indent=1))
        print(f"\n{len(todo)} findings match no known defect and are not adjudicated yet: bench/review/pr401-unmatched.json")


def main(a: list[str]) -> int:
    if not a or a[0] not in ("run", "score"):
        raise SystemExit(__doc__)
    arms = a[a.index("--arms") + 1].split(",") if "--arms" in a else ["nodevkb", "devkb"]
    if a[0] == "score":
        score(arms)
        return 0
    reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 3
    par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 3
    env = toolenv.build(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "origin/main"], capture_output=True, text=True).stdout.strip())
    jobs = [(arm, r) for arm in arms for r in range(1, reps + 1)]
    random.Random(7).shuffle(jobs)
    with cf.ThreadPoolExecutor(par) as ex:
        for f in cf.as_completed([ex.submit(run_one, arm, r, env if arm == "devkb" else None) for arm, r in jobs]):
            print(f.result(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
