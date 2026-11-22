#!/usr/bin/env python3
"""Review any pull request two ways, with and without devkb, verify what the reviews report, and track the result (#316).

  reviewbench.py run PR [--reps 1]      two reviews of the PR's diff, the same model and prompt: `nodevkb` (no graph, no devkb command) and `devkb`
                                        (the graph built, devkb on the PATH, and devkb's pack of every changed code file given in the prompt).
                                        Fresh checkouts at the PR's base and head; nothing the PR's own text says about its defects reaches the reviewer.
  reviewbench.py verify PR              every finding's reproduction is run twice on a clean checkout of the PR's head, in a sandbox with no network
                                        (bubblewrap; without it nothing is run and the findings stay unverified). Reproduced = it exits 1 both times.
  reviewbench.py rows PR                one row per PR and arm appended to bench/review/results.jsonl: findings, reproduced, by severity, the groups
                                        only that arm found, cost, model calls, context, output tokens, wall time, devkb queries and hook decisions.
  reviewbench.py gate-input PR          FINDINGS.json for `bench/review/gate.py PR FINDINGS.json` from the verified findings.

A finding is a JSON object {"file", "line", "severity": "high|medium|low", "claim", "repro", "evidence"}; `repro` is a shell command run from the
repository root that exits 1 when the defect is present (the audit's format)."""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import shlex
import shutil
import statistics as st
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results.jsonl"
OUT = Path(os.environ.get("REVIEW_OUT") or Path.home() / ".cache" / "devkb" / "review-pr")
SEVERITIES = ("high", "medium", "low")
ARMS = ("nodevkb", "devkb")
NEAR = 12            # two findings in one file within this many lines are one defect group

PROMPT = """You are reviewing a GitHub pull request, checked out in the current directory. The pull request is the last commit: `git diff HEAD~1 HEAD`.

Title: {title}

Find real defects in the changed code: wrong results, regressions in what worked before or in code that depends on what changed, crashes on unusual input, and tests that would pass without the change.
Reproduce each one before you report it (run the code, a test, or a short script) and drop what you cannot show. You may not edit files or use the network.

Finish with a JSON array in a ```json block, at most 15 objects, each {{"file": "...", "line": N, "severity": "high|medium|low", "claim": "...", "repro": "a SELF-CONTAINED shell command, run from the repository root of a clean checkout, that exits 1 when the defect is present", "evidence": "what it printed"}}.
The repro must create everything it needs itself (inline `python3 -c`, a heredoc, or files written inside the command); it must not refer to any file you wrote outside the repository, such as /tmp/x.py, because it is run later on a fresh checkout with no network."""
NODEVKB = """

This repository may be devkb itself. For this review do not use devkb's command line to look at the repository under review: no `devkb ...` and no `python -m devkb...`."""
DEVKB = """

`devkb` is on your PATH and the repository's graph is built. Below is devkb's pack for each changed code file (the functions other files call, the files that depend on it, and the tests that reach it). Use it, and `devkb symbol|outline|uses|pack ...` for more.

{packs}"""


def sh(cmd, cwd=None, timeout=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})}, input=input)


def pr_facts(pr: int) -> dict:
    """{title, head, base, files}: the head from `refs/pull/N/head`, the base as the head's fork point from origin/main (a merged PR too)."""
    j = json.loads(sh(["gh", "pr", "view", str(pr), "--json", "title,files"], cwd=ROOT).stdout)
    sh(["git", "fetch", "-q", "origin", f"pull/{pr}/head:refs/review/pr{pr}", "+refs/heads/main:refs/remotes/origin/main"], cwd=ROOT)
    head = sh(["git", "rev-parse", f"refs/review/pr{pr}"], cwd=ROOT).stdout.strip()
    base = sh(["git", "merge-base", "origin/main", head], cwd=ROOT).stdout.strip()
    return {"title": j["title"], "head": head, "base": base, "files": [f["path"] for f in j["files"]]}


def tree(commit: str, dest: Path) -> None:
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", commit], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
    for n in (".claude", "AGENTS.md", "CLAUDE.md", ".mcp.json"):       # no devkb instructions or hooks in either arm
        p = dest / n
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


def checkout(w: Path, facts: dict) -> None:
    """A repository whose history is two commits: the base, and the PR on top of it, so `git diff HEAD~1 HEAD` is the PR and nothing later can leak a fix."""
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    git = lambda *a: sh(["git", "-c", "user.name=r", "-c", "user.email=r@e.x", *a], cwd=w)
    git("init", "-q")
    tree(facts["base"], w)
    git("add", "-A")
    git("commit", "-qm", "base")
    git("rm", "-rq", "--cached", ".")
    for p in w.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    tree(facts["head"], w)
    git("add", "-A")
    git("commit", "-qm", "the pull request")


def code_files(files: list[str]) -> list[str]:
    return [f for f in files if f.endswith((".py", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".ts", ".tsx", ".js", ".go", ".rs", ".java")) and not f.startswith(("docs/", "tests/"))]


def parse_findings(text: str) -> list[dict]:
    m = list(re.finditer(r"```json\s*(.*?)```", text or "", re.S))
    if not m:
        return []
    try:
        d = json.loads(m[-1].group(1))
    except ValueError:
        return []
    out = []
    for x in d if isinstance(d, list) else []:
        if isinstance(x, dict) and x.get("file") and x.get("severity") in SEVERITIES:
            out.append({"file": str(x["file"]), "line": int(x["line"]) if str(x.get("line", "")).isdigit() else 0, "severity": x["severity"],
                        "claim": str(x.get("claim", "")), "repro": str(x.get("repro", "")), "evidence": str(x.get("evidence", ""))})
    return out


def run_one(pr: int, facts: dict, arm: str, rep: int, env: dict | None) -> str:
    import storybench as sb
    tag = f"{arm}-r{rep}"
    out = OUT / f"pr{pr}" / tag
    if (out / "score.json").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = OUT / f"pr{pr}" / "work" / tag
    t0 = time.time()
    checkout(w, facts)
    path = os.environ["PATH"]
    packs = ""
    if env:
        wrap = w.parent / (w.name + ".bin")
        wrap.mkdir(exist_ok=True)
        (wrap / "devkb").write_text(f'#!/bin/sh\nexec "{env["bin"]}" "$@"\n')
        (wrap / "devkb").chmod(0o755)
        sh([env["bin"], "build", "--project", str(w)], cwd=w, timeout=900)
        path = f"{wrap}:{path}"
        packs = "\n\n".join(f"### {f}\n" + sh([env["bin"], "pack", "--project", str(w), "file", f], cwd=w, timeout=120).stdout[:6000] for f in code_files(facts["files"])[:12])
    (out / "no-mcp.json").write_text('{"mcpServers": {}}')
    deny = ["Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)", "Bash(wget:*)"]
    if not env:
        deny += ["Bash(devkb:*)", "Bash(python -m devkb:*)", "Bash(python3 -m devkb:*)", "Bash(.venv/bin/devkb:*)"]
    cmd = ["claude", "-p", "--model", sb.MODEL, "--setting-sources", "local", "--output-format", "stream-json", "--verbose", "--max-turns", "80",
           "--max-budget-usd", "8", "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", str(out / "no-mcp.json"),
           "--no-session-persistence", "--allowedTools", "Bash", "Read", "Grep", "Glob", "--disallowedTools", *deny]
    prompt = PROMPT.format(title=facts["title"]) + (DEVKB.format(packs=packs) if env else NODEVKB)
    with open(out / "stream.jsonl", "w") as so, open(out / "stderr.log", "w") as se:
        p = subprocess.run(cmd, cwd=w, env={**os.environ, "PATH": path}, input=prompt, text=True, stdout=so, stderr=se, timeout=3000)
    ev = [json.loads(line) for line in open(out / "stream.jsonl") if line.startswith("{")]
    res = next((x for x in reversed(ev) if x.get("type") == "result"), {})
    row = {"run": tag, "arm": arm, "rep": rep, "exit": p.returncode, "seconds": round(time.time() - t0), "result": res.get("result") or "",
           **sb.transcript(out / "stream.jsonl")}
    row.pop("hook_first_output", None)
    (out / "score.json").write_text(json.dumps(row))
    shutil.rmtree(w, ignore_errors=True)
    shutil.rmtree(w.parent / (w.name + ".bin"), ignore_errors=True)
    return f"done {pr}/{tag} exit={p.returncode} turns={row['turns']} cost=${row['cost']} devkb={row['devkb_nav']} {row['seconds']}s"


# ---- verification --------------------------------------------------------------------------------------------------------------------

def sandbox(cmd: str, work: Path, timeout: int = 120) -> int | None:
    """Run a reproduction in `work` with no network, no home directory and a read-only system (bubblewrap). None when it cannot be sandboxed:
    a model's command is never run unboxed."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return None
    args = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    for d in ("/usr", "/etc", "/opt", "/lib", "/lib64", "/bin", "/sbin"):
        if Path(d).is_symlink():
            args += ["--symlink", os.readlink(d), d]
        elif Path(d).is_dir():
            args += ["--ro-bind", d, d]
    venv = Path(sys.executable).parent.parent
    args += ["--ro-bind", str(venv), str(venv)] if not str(venv).startswith(("/usr", "/opt")) else []
    args += ["--bind", str(work), str(work), "--chdir", str(work), "--clearenv", "--setenv", "HOME", "/tmp", "--setenv", "PATH",
             f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin", "--setenv", "PYTHONPATH", str(work), "--", "bash", "-c", cmd]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        return 124


def verify_finding(f: dict, facts: dict, run=sandbox) -> dict:
    """Reproduced when the finding's command exits 1 on two separate clean checkouts of the PR head; a finding with no command, or a machine without a
    sandbox, stays unverified (never counted as a defect)."""
    if not f.get("repro", "").strip():
        return {**f, "reproduced": False, "why": "no reproduction given"}
    codes = []
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="reviewverify") as d:
            w = Path(d) / "w"
            w.mkdir()
            tree(facts["head"], w)
            codes.append(run(f["repro"], w))
    if None in codes:
        return {**f, "reproduced": False, "why": "no sandbox (bubblewrap) on this machine"}
    return {**f, "reproduced": codes == [1, 1], "why": f"exit codes {codes}"}


def groups(per_arm: dict[str, list[dict]]) -> dict[str, int]:
    """Defect groups only one arm found: findings of the other arms in the same file within NEAR lines are the same defect."""
    only = {a: 0 for a in per_arm}
    for a, fs in per_arm.items():
        seen: list[tuple[str, int]] = []
        for f in (x for x in fs if x.get("reproduced")):
            if any(f["file"] == sf and abs(f["line"] - sl) <= NEAR for sf, sl in seen):
                continue                                           # the same group within this arm
            seen.append((f["file"], f["line"]))
            others = [g for b, gs in per_arm.items() if b != a for g in gs if g.get("reproduced")]
            if not any(g["file"] == f["file"] and abs(g["line"] - f["line"]) <= NEAR for g in others):
                only[a] += 1
    return only


def arm_row(pr: int, arm: str, runs: list[dict], per_arm: dict[str, list[dict]]) -> dict:
    fs = per_arm[arm]
    ok = [f for f in fs if f.get("reproduced")]
    mean = lambda k: round(st.mean(r.get(k) or 0 for r in runs), 3) if runs else 0
    return {"pr": pr, "arm": arm, "reviews": len(runs), "findings": len(fs), "reproduced": len(ok),
            "by_severity": {s: sum(1 for f in ok if f["severity"] == s) for s in SEVERITIES}, "only_this_arm": groups(per_arm)[arm],
            "cost": mean("cost"), "model_calls": mean("model_calls"), "ctx_tokens": mean("ctx_tokens"), "out_tokens": mean("out_tokens"),
            "seconds": mean("seconds"), "devkb_queries": mean("devkb_nav"), "hook_decisions": mean("guardrail_fired")}


def load_findings(pr: int) -> dict[str, list[dict]]:
    p = OUT / f"pr{pr}" / "verified.json"
    return json.loads(p.read_text()) if p.exists() else {}


def gate_input(per_arm: dict[str, list[dict]]) -> list[dict]:
    """`gate.py` findings: each reproduced defect group with its severity per arm and whether it is still open (a new review has no fixes yet)."""
    out: list[dict] = []
    for a, fs in per_arm.items():
        for f in (x for x in fs if x.get("reproduced")):
            hit = next((o for o in out if o["file"] == f["file"] and abs(o["line"] - f["line"]) <= NEAR), None)
            if hit:
                hit["arms"][a] = f["severity"]
                hit["severity"] = min((hit["severity"], f["severity"]), key=SEVERITIES.index)
            else:
                out.append({"file": f["file"], "line": f["line"], "severity": f["severity"], "open": True, "arms": {a: f["severity"]}})
    return out


def main(a: list[str]) -> int:
    if len(a) < 2 or a[0] not in ("run", "verify", "rows", "gate-input"):
        raise SystemExit(__doc__)
    pr = int(a[1])
    base = OUT / f"pr{pr}"
    if a[0] == "run":
        sys.path.insert(0, str(ROOT / "bench" / "policy"))
        import toolenv
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 1
        facts = pr_facts(pr)
        base.mkdir(parents=True, exist_ok=True)
        (base / "facts.json").write_text(json.dumps(facts))
        env = toolenv.build(sh(["git", "rev-parse", "origin/main"], cwd=ROOT).stdout.strip())
        jobs = [(arm, r) for arm in ARMS for r in range(1, reps + 1)]
        with cf.ThreadPoolExecutor(len(jobs)) as ex:
            for f in cf.as_completed([ex.submit(run_one, pr, facts, arm, r, env if arm == "devkb" else None) for arm, r in jobs]):
                print(f.result(), flush=True)
        return 0
    facts = json.loads((base / "facts.json").read_text())
    scores = {arm: [json.loads(p.read_text()) for p in sorted(base.glob(f"{arm}-r*/score.json"))] for arm in ARMS}
    if a[0] == "verify":
        per_arm = {arm: [verify_finding(f, facts) for r in rs for f in parse_findings(r["result"])] for arm, rs in scores.items()}
        (base / "verified.json").write_text(json.dumps(per_arm, indent=1))
        print({arm: f"{sum(1 for f in fs if f['reproduced'])} of {len(fs)} reproduced" for arm, fs in per_arm.items()})
        return 0
    per_arm = load_findings(pr)
    if not per_arm:
        raise SystemExit(f"run `reviewbench.py verify {pr}` first")
    if a[0] == "rows":
        rows = [arm_row(pr, arm, scores[arm], per_arm) for arm in ARMS if scores.get(arm)]
        with open(RESULTS, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(json.dumps(rows, indent=1))
        return 0
    print(json.dumps(gate_input(per_arm), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
