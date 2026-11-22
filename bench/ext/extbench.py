#!/usr/bin/env python3
"""A live agent benchmark in another repository (yaml-cpp, C++): bug-fix tickets built from the repository's own history, with the arm's
devkb as the agent's `devkb` command. Needed because on devkb's own tickets the agent's `devkb` is the code under edit, so no devkb
change can be tested live (docs/analysis/improvement-plan-data-loop.md).

A ticket is a real fix commit: the base is its parent, the issue text describes the symptom (written without the fix), and the hidden
check copies the fix commit's own test files over the agent's tree, builds and runs the whole test binary (it passes only if the new
tests and every older test pass). The agent works in a fresh clone at the base with a one-commit history, so the fix cannot be read
from `git log`. Arms: `none` (no devkb on the PATH), and devkb arms named by a commit: `orig=SHA`, `ship=SHA` (any labels). Each devkb
arm gets that commit's `devkb` (bench/policy/toolenv.py), its graph built by it, its AGENTS.md policy block and its guardrail hooks.

  extbench.py validate [TICKET ...]                 the hidden check fails at the base and passes at the fix
  extbench.py run --arms none,orig=SHA,ship=SHA [--reps 3] [--parallel 4] [--resume] [--clean] [TICKET ...]

--clean: the checkout is under a root whose path names neither devkb nor an arm (EXT_CLEAN_ROOT, default ~/.cache/ext-clean/wXXXXXXXX), and
Claude runs with an isolated config directory (no user plugins, skills, hooks or memory; the login is linked, not copied). Found necessary
when an arm's label in the checkout path could not be ruled out as the cause of a 10% to 47% jump in devkb use (docs/analysis/cpp-yaml-benchmark.md).
  extbench.py table --arms ...                      the table, from ~/.cache/devkb/ext/results.jsonl

Runs and clones live under ~/.cache/devkb/ext (never in this repository); the rows keep no local paths."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
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

EXT = Path.home() / ".cache" / "devkb" / "ext"
REPO = EXT / "yaml-cpp"
RUNS = EXT / "runs"
WORK = EXT / "work"
RESULTS = EXT / "results.jsonl"
CLEAN = Path(os.environ.get("EXT_CLEAN_ROOT") or Path.home() / ".cache" / "ext-clean")   # --clean: a root whose path names neither devkb nor an arm
LEAKS = ("devkb", "orig", "ship", "none", "main", "claude", "bench")                       # words an agent could read the arm or the tool from
BUILD = "cmake -S . -B build -DYAML_CPP_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release && cmake --build build -j8 && ./build/test/yaml-cpp-tests"
TIMEOUT = 2400


def sh(cmd, cwd=None, timeout=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})}, input=input)


def tickets() -> list[dict]:
    out = json.loads((HERE / "tickets-yaml-cpp.json").read_text())
    for t in out:
        t["base"] = sh(["git", "-C", str(REPO), "rev-parse", t["fix"] + "^"]).stdout.strip()
    return out


def checkout(commit: str, dest: Path) -> None:
    """The tree at `commit` with a one-commit history of its own: no fix to read from `git log`."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(REPO), "archive", commit], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=b", "-c", "user.email=b@e.x", "commit", "-qm", "base"]):
        sh(["git", *c], cwd=dest)


def hidden_check(w: Path, t: dict) -> dict:
    """Copy the fix commit's test files over the tree, build, run the whole test binary."""
    for f in t["tests"]:
        (w / f).write_text(sh(["git", "-C", str(REPO), "show", f"{t['fix']}:{f}"]).stdout)
    b = sh(["bash", "-c", "cmake -S . -B build -DYAML_CPP_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1 && cmake --build build -j8 2>&1 | tail -5"],
           cwd=w, timeout=1500)
    exe = w / "build" / "test" / "yaml-cpp-tests"
    if not exe.exists():
        return {"pass": False, "built": False, "failed": [], "tail": b.stdout[-300:]}
    r = sh([str(exe)], cwd=w, timeout=900)
    failed = re.findall(r"^\[  FAILED  \] (\S+)", r.stdout, re.M)
    return {"pass": r.returncode == 0, "built": True, "failed": sorted(set(failed))[:8], "tail": r.stdout[-200:]}


def validate(ids: list[str]) -> None:
    for t in tickets():
        if ids and t["id"] not in ids:
            continue
        res = {}
        for label, commit in (("base+tests", t["base"]), ("fix", t["fix"])):
            w = WORK / f"validate-{t['id']}-{label.split('+')[0]}"
            checkout(commit, w)
            res[label] = hidden_check(w, t)
            shutil.rmtree(w, ignore_errors=True)
        ok = (not res["base+tests"]["pass"]) and res["fix"]["pass"]
        print(f"{t['id']} {t['fix']}: base + the fix's tests -> {'FAIL' if not res['base+tests']['pass'] else 'pass'} ({res['base+tests']['failed'][:2]}), "
              f"fix -> {'pass' if res['fix']['pass'] else 'FAIL'}  => {'valid ticket' if ok else 'INVALID'}", flush=True)


def prompt(t: dict) -> str:
    return (f"You are working in a clone of the C++ library yaml-cpp (the current directory). Fix this bug in the library.\n\n"
            f"# {t['title']}\n\n{t['body']}\n\n"
            f"Build and test with: `{BUILD}` (the first build takes about 90 seconds; run builds in the foreground). "
            "Add a regression test to the existing test files under test/. Do not commit. Stop when the fix is in and the whole test suite passes.")


def arm_env(spec: str) -> tuple[str, dict | None]:
    label, _, sha = spec.partition("=")
    return label, (toolenv.build(sha) if sha else None)


def prepare(t: dict, arm: str, env: dict | None, w: Path) -> dict:
    checkout(t["base"], w)
    path = os.environ["PATH"]
    if env:
        (w.parent / (w.name + ".bin")).mkdir(parents=True, exist_ok=True)
        wrap = w.parent / (w.name + ".bin") / "devkb"
        wrap.write_text(f'#!/bin/sh\nexec "{env["bin"]}" "$@"\n')
        wrap.chmod(0o755)
        path = f"{wrap.parent}:{path}"
        sh([env["bin"], "init", "--project", str(w), "--no-build"], cwd=w)
        (w / ".mcp.json").unlink(missing_ok=True)                    # the shell is the interface, as in devkb's own repository
        sh([env["bin"], "build", "--project", str(w)], cwd=w, timeout=900)
        (w / ".claude").mkdir(exist_ok=True)
        (w / ".claude" / "settings.json").write_text(json.dumps({"hooks": toolenv.hooks_settings(env)}, indent=2))
    sh(["git", "-C", str(w), "add", "-A"])
    sh(["git", "-C", str(w), "-c", "user.name=b", "-c", "user.email=b@e.x", "commit", "-qm", "policy and graph"])
    return {"PATH": path}


def clean_config() -> Path:
    """An isolated Claude config directory: no user plugins, skills, hooks, memory or MCP connectors; the existing login is linked, not copied."""
    cfg = CLEAN / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    cred = cfg / ".credentials.json"
    if not (cred.is_symlink() or cred.exists()):
        try:
            cred.symlink_to(Path.home() / ".claude" / ".credentials.json")
        except FileExistsError:            # another worker made it first
            pass
    return cfg


def run_one(t: dict, spec: str, rep: int, clean: bool = False) -> str:
    arm, env = arm_env(spec)
    tag = f"{t['id']}-{arm}-r{rep}"
    out = RUNS / tag
    if (out / "score.json").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    opaque = "w" + hashlib.sha1(f"{tag}:{time.time()}".encode()).hexdigest()[:8]           # not the tag: it names the arm
    w = (CLEAN / opaque) if clean else WORK / tag
    leaks = [x for x in LEAKS if x in str(w).lower()] if clean else None
    if leaks:
        return f"refused {tag}: the checkout path {w} contains {leaks}"
    t0 = time.time()
    try:
        e = prepare(t, arm, env, w)
        mcp = out / "no-mcp.json"
        mcp.write_text('{"mcpServers": {}}')
        deny = ["Bash(git push:*)", "WebFetch", "WebSearch"] + (["Bash(devkb:*)"] if not env else [])
        cmd = ["claude", "-p", "--model", sb.MODEL, "--setting-sources", "project,local", "--output-format", "stream-json", "--verbose", "--max-turns", "90",
               "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", str(mcp), "--include-hook-events",
               "--allowedTools", "Bash", "Read", "Edit", "Write", "Grep", "Glob", "--disallowedTools", *deny]
        with open(out / "stream.jsonl", "w") as so, open(out / "stderr.log", "w") as se:
            run_env = {**os.environ, **e, **({"CLAUDE_CONFIG_DIR": str(clean_config())} if clean else {})}
            p = subprocess.run(cmd, cwd=w, env=run_env, input=prompt(t), text=True, stdout=so, stderr=se, timeout=TIMEOUT)
        code = p.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    except Exception as ex:  # noqa: BLE001
        (out / "error.txt").write_text(f"{type(ex).__name__}: {ex}")
        return f"error {tag}: {ex}"
    check = hidden_check(w, t) if w.exists() else {"pass": False}
    row = {"run": tag, "ticket": t["id"], "arm": arm, "rep": rep, "exit": code, "seconds": round(time.time() - t0), "devkb_commit": (env or {}).get("commit", "")[:7] or None,
           "clean": ({"cwd_has": [x for x in LEAKS if x in str(w).lower()], "config_isolated": True} if clean else None),
           "pass": check["pass"], "built": check.get("built"), "failed": check.get("failed", []), **sb.transcript(out / "stream.jsonl")}
    row.pop("hook_first_output", None)
    (out / "score.json").write_text(json.dumps(row))
    with open(RESULTS, "a") as f:
        f.write(json.dumps({k: v for k, v in row.items() if k not in ("session",)}) + "\n")
    shutil.rmtree(w, ignore_errors=True)
    shutil.rmtree(w.parent / (w.name + ".bin"), ignore_errors=True)
    return f"done {tag} exit={code} pass={check['pass']} turns={row['turns']} cost=${row['cost']} devkb={row['devkb_nav']} {row['seconds']}s"


def table(arms: list[str]) -> None:
    rows = [json.loads(l) for l in open(RESULTS)] if RESULTS.exists() else []
    labels = [a.partition("=")[0] for a in arms]
    print("| ticket | arm | n | pass | turns | search | read* | devkb nav | pack calls | refetch | ctx tok k | out tok k | cost $ |\n|" + "---|" * 13)
    for tid in sorted({r["ticket"] for r in rows}):
        for a in labels:
            v = [r for r in rows if r["ticket"] == tid and r["arm"] == a and r.get("turns")]
            if not v:
                continue
            c = lambda r, k: (r.get("calls") or {}).get(k, 0)
            rf = [r["refetch"] for r in v if r.get("refetch")]
            print(f"| {tid} | {a} | {len(v)} | {sum(1 for r in v if r['pass'])}/{len(v)} | {st.mean(r['turns'] for r in v):.1f} | {st.mean(c(r, 'search') for r in v):.1f} | "
                  f"{st.mean(c(r, 'read') for r in v):.1f} | {st.mean(r['devkb_nav'] for r in v):.1f} | - | {sum(x['refetched'] for x in rf)}/{sum(x['queries'] for x in rf)} | "
                  f"{st.mean(r['ctx_tokens'] for r in v) / 1e3:.0f} | {st.mean(r.get('out_tokens', 0) for r in v) / 1e3:.1f} | {st.mean(r['cost'] for r in v):.2f} |")


def main(a: list[str]) -> int:
    if not a or a[0] not in ("validate", "run", "table"):
        raise SystemExit(__doc__)
    arms = a[a.index("--arms") + 1].split(",") if "--arms" in a else ["none"]
    ids = [x for x in a[1:] if re.fullmatch(r"y\d+", x)]
    if a[0] == "validate":
        validate(ids)
    elif a[0] == "table":
        table(arms)
    else:
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 3
        par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 4
        ts = [t for t in tickets() if not ids or t["id"] in ids]
        jobs = [(t, s, r) for t in ts for s in arms for r in range(1, reps + 1)]
        done = [f"{t['id']}-{s.partition('=')[0]}-r{r}" for t, s, r in jobs if (RUNS / f"{t['id']}-{s.partition('=')[0]}-r{r}" / "score.json").exists()]
        if done and "--resume" not in a:
            raise SystemExit(f"{len(done)} of {len(jobs)} runs already exist ({', '.join(done[:5])}...): archive them or pass --resume")
        for s in arms:
            arm_env(s)                                                    # build the tool environments before any run starts
        random.Random(5).shuffle(jobs)
        clean = "--clean" in a
        with cf.ThreadPoolExecutor(par) as ex:
            for f in cf.as_completed([ex.submit(run_one, *j, clean) for j in jobs]):
                print(f.result(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
