"""Release audit of v0.2.12 -> main as a bi-arm benchmark: three reviewers (areas), each run without devkb and with
the 0.2.13 hook (D1 on), same model and harness as the policy benchmark. Each finding carries a reproduction script that
exits non-zero while the bug is present; scoring reproduces it twice on a clean checkout of main.

Usage: auditbench.py run [--reps N] [--parallel N] | verify | report OUT.md
"""
import concurrent.futures as cf
import json
import os
import re
import shutil
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
H = Path(os.environ.get("DEVKB_POLICY_HARNESS", Path(__file__).resolve().parents[2] / "policy"))   # the policy harness (bench/policy)
sys.path.insert(0, str(H))
import policybench as pb  # noqa: E402
import storybench as sb  # noqa: E402
import toolenv  # noqa: E402

V0212 = "268edf8cd030ca46c12fcc336a834d6ad15d3a2c"
ARMS = ("nonekeep", "main")
TICKETS = dict(line.split("\t", 1) for line in (HERE / "tickets.tsv").read_text().splitlines())

AREAS = {
    "guardrail": {
        "files": ["scripts/devkb_guardrail.py", "scripts/devkb_guardrail_post.py", "devkb/misses.py", "devkb/outcomes.py",
                  "devkb/read_tools.py", "AGENTS.md"],
        "tickets": [171, 175, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 211, 214, 215, 216, 217, 218, 267,
                    137, 138, 128],
        "focus": "the PreToolUse search guardrail and its PostToolUse miss log: intent classification (13 classes, "
                 "SPEC-DKB-007), the graph question per intent, answer shape and size, replace / alongside / pass-through, "
                 "the stale-graph rule, the D1 teach line (on by default), guardrail-stats and the miss log. Besides "
                 "checking behaviour against SPEC-DKB-007 (docs/specs/SPEC-DKB-007_search-intent.md), replay recorded agent "
                 "searches from audit/searches.jsonl (real searches agents made, one JSON object per line: tool and input) "
                 "through scripts/devkb_guardrail.py on this repository and judge each answer against what the search asked: "
                 "an answer to a different question, an answer larger than grep's output, or a replacement that hides lines "
                 "grep would print is a finding even when the spec's decision table allows it.",
    },
    "graph": {
        "files": ["devkb/build_symbols.py", "devkb/packs.py", "devkb/cpp_resolve.py", "devkb/cpp_symbols.py",
                  "devkb/cpp_graph.py", "devkb/cli.py", "devkb/process_api.py", "devkb/extractors/flows.py"],
        "tickets": [118, 120, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 212, 228],
        "focus": "the graph build and the query tools: Python call resolution (fields and constants as targets, re-exports, "
                 "constant reads and string keys), packs (change / refactor / file), the C/C++ resolver (macro expansion with "
                 "the union rule, member calls through declared types, TEST_F fixtures, arity, overload spans), build-time "
                 "complexity, deterministic flows, and the CLI's errors. The C/C++ corpus is in ./corpus/ (cJSON, leveldb, "
                 "fmt). A wrong edge, a missing edge that a pack still calls Complete, or a quadratic build is a finding.",
    },
    "ops": {
        "files": ["ops/triage/triage.py", "bench/policy/policybench.py", "bench/policy/storybench.py",
                  "bench/policy/release_table.py", "bench/policy/toolenv.py", "bench/policy/remeasure.py",
                  "bench/audit/toolmix.py", "bench/perf_release.py", "bench/exploration/listing_then_read.py"],
        "tickets": [205, 206, 207, 208, 209, 210, 221, 222, 223, 224, 225, 258, 260],
        "focus": "the triage / handle / feedback daemon (including the security fix for advisory GHSA-m9p8-8jv9-c7p2: agents "
                 "in an empty directory with only their file tools, untrusted code only in a bubblewrap sandbox, pinned host "
                 "git, sanitised posted text, a random prompt fence) and the benchmark harness (checkout templates and their "
                 "locks, tool environments pinned to commits, scoring as runs end, the flaky-suite rule, transcript counts "
                 "and the navigation / self-test rule, the release table's statistics). A way untrusted text or code reaches "
                 "the host, a run scored wrongly, or a number in the release table computed wrongly is a finding. Do not "
                 "run the daemon against GitHub and do not post anything; test with fixtures.",
    },
}

PROMPT = """You are auditing the devkb repository (a code-graph tool for coding agents; Python; its venv is .venv, run
Python as .venv/bin/python) for its 0.2.13 release: every change from v0.2.12 (commit {v}) to HEAD in your area. List
them with `git log --oneline {v}..HEAD -- <files>` and `git diff {v} HEAD -- <files>`.

Your area: {area}. Its files: {files}.
The tickets merged in your area (you cannot open GitHub; the titles are here):
{tickets}

What to look at: {focus}

Find defects: behaviour that is wrong for a user or an agent, a regression from v0.2.12, a fix that is incomplete or
breaks something else, an untested path, or a security problem. Report only what you have reproduced. For each finding:
1. write a reproduction script audit/repro/<id>.py that exits with status 1 while the defect is present and 0 once it is
   fixed, prints what happens and what was expected, and needs nothing outside this checkout (build any fixture under a
   temporary directory; run devkb as .venv/bin/python -m devkb.cli);
2. run it twice and see it exit 1 both times;
3. add the finding to audit/findings.json, a JSON list of objects with the keys: id (short slug), title (the outcome a
   user would want, as a ticket title), severity (high, medium or low), where (file:line), actual, expected,
   why_it_matters, repro (audit/repro/<id>.py).

Do not change any file outside audit/. Do not push, post or open anything. When you are done, end with one line:
FINDINGS <number of findings in audit/findings.json>."""


def searches(w: Path) -> None:
    """The recorded agent searches (0.2.12 benchmark sessions) for the guardrail reviewer, paths mapped to this checkout."""
    src = Path(os.environ["DEVKB_REPLAY_SEARCHES"])            # recorded searches, one JSON object per line (tool, input)
    out = []
    for line in src.read_text().splitlines():
        r = json.loads(line)
        s = json.dumps({"tool": r["tool"], "input": r["input"]}).replace(os.environ.get("DEVKB_REPLAY_ROOT", "\0"), ".")
        if "/home/" not in s:
            out.append(s)
    (w / "audit").mkdir(exist_ok=True)
    (w / "audit" / "searches.jsonl").write_text("\n".join(out) + "\n")


def run_one(area: str, arm: str, rep: int) -> str:
    tag = f"a{area}-{arm}-r{rep}"
    out = HERE / "runs" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = HERE / "work" / tag
    try:
        pb.from_template(pb.template_for(arm), w)
        (w / "audit" / "repro").mkdir(parents=True, exist_ok=True)
        if area == "guardrail":
            searches(w)
        a = AREAS[area]
        prompt = PROMPT.format(v=V0212, area=area, files=", ".join(a["files"]), focus=a["focus"],
                               tickets="\n".join(f"- #{t}: {TICKETS.get(str(t), '')}" for t in a["tickets"]))
        mcp = str(HERE / "no-mcp.json")
        Path(mcp).write_text(json.dumps({"mcpServers": {}}))
        deny = sb.DENY + (["Bash(devkb:*)"] if arm == "nonekeep" else [])
        env_bin = pb.tool_of(arm, toolenv.build(pb.ENV_REF[arm]()) if arm in pb.ENV_REF else None)
        cmd = ["claude", "-p", prompt, "--model", sb.MODEL, *pb.SOURCES, "--output-format", "stream-json", "--verbose",
               "--max-turns", "200", "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", mcp,
               "--allowedTools", *sb.ALLOW, "--disallowedTools", *deny]
        env = dict(os.environ, DEVKB_GUARDRAIL="0" if arm == "nonekeep" else "1",
                   PATH=f"{Path(env_bin).parent}:{w / '.venv' / 'bin'}:{os.environ['PATH']}", **pb.ARM_ENV.get(arm, {}))
        (out / "arm.json").write_text((w / ".bench-arm.json").read_text())
        t0 = time.time()
        with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
            try:
                code = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=5400).returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0)}))
        return f"done {tag} exit={code} {round(time.time() - t0)}s"
    except Exception as e:  # noqa: BLE001  recorded, never a silent loss
        (out / "end").write_text(json.dumps({"exit": "error", "seconds": 0, "error": f"{type(e).__name__}: {e}"[-400:]}))
        return f"error {tag}: {e}"


def verify() -> None:
    """Each finding's repro, copied into a fresh copy of main's checkout, must exit 1 twice."""
    t = pb.template_for("main")
    rows = []
    for out in sorted((HERE / "runs").glob("a*-*-r*")):
        w = HERE / "work" / out.name
        f = w / "audit" / "findings.json"
        try:
            found = json.loads(f.read_text()) if f.exists() else []
        except ValueError:
            found = []
        for x in found if isinstance(found, list) else []:
            rp = w / str(x.get("repro", ""))
            ok, codes, outs = False, [], []
            if rp.is_file():
                clean = HERE / "verify" / f"{out.name}-{x.get('id', 'x')}"
                if not clean.exists():
                    pb.from_template(t, clean)
                if (clean / "audit").exists():
                    shutil.rmtree(clean / "audit")
                shutil.copytree(w / "audit", clean / "audit", ignore=shutil.ignore_patterns("__pycache__", "findings.json"))
                dst = clean / "audit" / "repro" / rp.name     # helpers the reviewer wrote beside it (audit/*.py) come along
                for _ in range(2):
                    try:
                        c = subprocess.run([str(clean / ".venv/bin/python"), str(dst)], cwd=clean, capture_output=True,
                                           text=True, timeout=600,
                                           env=dict(os.environ, PYTHONPATH=f"{clean / 'audit'}:{clean / 'audit' / 'repro'}"))
                        crashed = "Traceback (most recent call last)" in c.stderr     # exit 1 from a crash is not a repro
                        codes.append("crash" if crashed else c.returncode)
                        outs.append((c.stdout + c.stderr)[-600:])
                    except subprocess.TimeoutExpired:
                        codes.append("timeout")
                ok = codes == [1, 1]
            rows.append({"run": out.name, **{k: x.get(k) for k in ("id", "title", "severity", "where", "repro")},
                         "codes": codes, "reproduced": ok, "output": outs[-1] if outs else ""})
            print(out.name, x.get("id"), x.get("severity"), "REPRODUCED" if ok else f"not reproduced {codes}", flush=True)
    (HERE / "verified.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    a = sys.argv[1:]
    main = subprocess.run(["git", "-C", str(sb.REPO), "rev-parse", "origin/main"], capture_output=True, text=True).stdout.strip()
    os.environ.setdefault("POLICY_MAIN", main)          # both arms and main's devkb pinned to one commit, as policybench does
    for k, v in pb.BASES.items():
        if v == "origin/main":
            pb.BASES[k] = os.environ["POLICY_MAIN"]
    if a[0] == "run":
        print("pinned to main", os.environ["POLICY_MAIN"][:12], flush=True)
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 2
        par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 6
        jobs = [(area, arm, r) for area in AREAS for arm in ARMS for r in range(1, reps + 1)]
        with cf.ThreadPoolExecutor(par) as ex:
            for fut in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
                print(fut.result(), flush=True)
    elif a[0] == "verify":
        verify()
