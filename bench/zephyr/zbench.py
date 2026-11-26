#!/usr/bin/env python3
"""Zephyr benchmark runner: devkb 0.2.15 against codebase-memory-mcp against nothing (#447).

    zbench.py run   PR ARM REP        one agent run: prepare the arm, run `claude -p`, apply the hidden check, write the record
    zbench.py smoke ARM               a cheap navigation question that proves the arm's tools are reachable and answer correctly
    zbench.py check PR                the hidden check alone, base commit against fix commit (no agent)
    zbench.py isolation               one cheap run that tries to write and delete outside its run; judged from outside the agent (#451)

Every agent runs sandboxed with its own temp and cache folders (`isolation.py`); a run refuses to start without the sandbox.

Arms:  none   Claude Code's own Read/Grep/Glob/Bash
       devkb  PyPI devkb[mcp] 0.2.15, set up as its README does (`devkb init --toolset lean --claude-hook`; --no-build because the graph, built
              beforehand at the task's base commit, is copied in), plus the grep hook of the 0.2.15 tag (`scripts/devkb_guardrail.py` and its
              post hook, wired as the repository's own `.claude/settings.json` wires them: PreToolUse `Read|Grep|Bash`, PostToolUse `Grep|Bash`).
              The wheel does not contain that hook; the owner's setup for this benchmark includes it. It runs with the venv's python (it imports
              devkb) and with a per-run HOME, so its decision log (`$HOME/.claude/hooks/devkb-guardrail.log`) is the run's own
       cbm    codebase-memory-mcp from install.sh, set up as `install --clients=claude` does it: MCP entry, skill, three subagents and
              the hook-augment hooks, the index built beforehand in the run's own cache (CBM_CACHE_DIR)

Everything is under ZBENCH_RUN (default: `run/` of this checkout): tasks/<PR>/{task.json,issue.md}, hidden/<PR>/ (kept out of every
checkout), tmpl/dkb-<PR>/ (the base checkout with its devkb graph), zephyr-src/ (the clone). Checkouts live in ~/.cache/devkb/zbench, never
under ~/.claude (0.2.15: a work directory there invalidated every run). Records go to ZBENCH_RUN/zbench-runs/<tag>/.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation  # noqa: E402
import metrics  # noqa: E402

RUN = Path(os.environ.get("ZBENCH_RUN") or Path(__file__).resolve().parents[2] / "run")
ZSRC = RUN / "zephyr-src"
WORK = Path.home() / ".cache" / "devkb" / "zbench"
OUT = RUN / "zbench-runs"
MODEL = os.environ.get("ZBENCH_MODEL", "claude-sonnet-5-5")
DEVKB_BIN = RUN / "devkb-0.2.15" / "venv" / "bin"
CBM = RUN / "cbm" / "bin" / "codebase-memory-mcp"
GUARDRAIL = RUN / "guardrail-0.2.15" / "scripts"        # `git show v0.2.15:scripts/devkb_guardrail{,_post}.py`: not in the wheel, so taken from the tag
CBM_TEMPLATE = RUN / "cbm" / "claude-config"          # what `install --clients=claude` wrote, once, with the binary path rewritten
ZPATH = [RUN / "zephyr-venv" / "bin", RUN / "zephyr-tools" / "hosttools" / "sysroots" / "aarch64-pokysdk-linux" / "usr" / "bin"]
ARMS = ("none", "devkb", "cbm")
MAX_TURNS = os.environ.get("ZBENCH_MAX_TURNS", "150")
RUN_TIMEOUT = int(os.environ.get("ZBENCH_TIMEOUT", "5400"))

ALLOW = ["Bash", "Read", "Edit", "Write", "MultiEdit", "Glob", "Grep"]
DENY = ["Bash(git push:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(gh:*)", "WebFetch", "WebSearch"]

PROMPT = """You are working in a checkout of the Zephyr RTOS repository (the current directory). Resolve the GitHub issue below by changing the
source code. The fix will be checked by tests you cannot see, which exercise the behaviour the issue describes. You may add tests of your own.

To build and run a test on the simulator (the environment is set up):
  cmake -GNinja -DBOARD=native_sim/native/64 -S {test_dir} -B build && ninja -C build && ./build/zephyr/zephyr.exe
{test_dir} is the test directory closest to this issue.

Finish with a short summary of what you changed and why.

---
{issue}
"""

SMOKE_PROMPT = """In this Zephyr checkout, find where the function `tcp_options_check` is defined and name every function that calls it.
Answer in two lines: `defined: <path>:<line>` and `callers: <comma separated names>`. Do not edit any file."""
SMOKE_EXPECT = {"defined": "subsys/net/ip/tcp.c", "callers": "tcp_in"}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def task(pr: str) -> dict:
    t = json.loads((RUN / "tasks" / pr / "task.json").read_text())
    t["pr"] = str(t["pr"])
    return t


def issue_text(pr: str) -> str:
    """The issue as written, except what would put the hidden check into the prompt: a regression-test patch the reporter attached (#447)."""
    text = (RUN / "tasks" / pr / "issue.md").read_text()
    text = re.sub(r"(?ms)^## Regression-only patch\b.*?(?=^## |\Z)", "", text)
    text = re.sub(r"(?m)^[^\n]*regression-only patch below[^\n]*\n(\s*\n```sh\n.*?\n```\n)?", "", text, flags=re.S)
    return text.strip() + "\n"


def clean_path() -> list[str]:
    """The machine's PATH without ~/.local/bin (a dev `devkb` lives there and would reach every arm), plus a directory holding only `claude`."""
    shim = RUN / "shims"
    shim.mkdir(exist_ok=True)
    real = shutil.which("claude")
    if real and not (shim / "claude").exists():
        (shim / "claude").symlink_to(real)
    drop = str(Path.home() / ".local" / "bin")
    return [str(shim)] + [p for p in os.environ["PATH"].split(":") if p != drop]


def env_for(arm: str, w: Path, run_dir: Path) -> dict:
    path = [str(p) for p in ZPATH]
    if arm == "devkb":
        path.insert(0, str(DEVKB_BIN))
    env = dict(os.environ, ZEPHYR_BASE=str(w), ZEPHYR_TOOLCHAIN_VARIANT="host", BASH_DEFAULT_TIMEOUT_MS="600000", BASH_MAX_TIMEOUT_MS="600000",
               PATH=":".join(path + clean_path()))
    if arm == "cbm":
        env["CBM_CACHE_DIR"] = str(run_dir / "cbm-cache")
    if arm == "devkb":
        env["DEVKB_GUARDRAIL_KEEP"] = "1"
    return env


def touched(w: Path) -> set[str]:
    """Files that differ from the commit: new or modified. Right after setup these are the arm's own (`devkb init` edits AGENTS.md, CLAUDE.md, .gitignore)."""
    out = sh(["git", "-C", str(w), "status", "--porcelain", "--untracked-files=all"]).stdout
    return {line[3:].strip('"') for line in out.splitlines() if len(line) > 3}


def prepare(t: dict, arm: str, tag: str, run_dir: Path, base: str | None = None) -> tuple[Path, dict]:
    """A fresh checkout at the task's base commit, set up for the arm. Returns it and what was timed or recorded on the way."""
    w = WORK / tag
    if w.exists():
        sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])
        shutil.rmtree(w, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    r = sh(["git", "-C", str(ZSRC), "worktree", "add", "--detach", str(w), base or t["base"]])
    if r.returncode:
        raise RuntimeError(f"worktree: {r.stderr[-300:]}")
    info: dict = {"arm": arm}
    env = env_for(arm, w, run_dir)
    if arm == "devkb":
        shutil.copytree(RUN / "tmpl" / f"dkb-{t['pr']}" / ".devkb", w / ".devkb")
        r = sh([str(DEVKB_BIN / "devkb"), "init", "--no-build", "--toolset", "lean", "--claude-hook"], cwd=w, env=env)
        info["init_rc"], info["init_out"] = r.returncode, (r.stdout + r.stderr)[-600:]
        info["guardrail_wired"] = wire_guardrail(w, run_dir)
    elif arm == "cbm":
        (run_dir / "cbm-cache").mkdir(parents=True, exist_ok=True)
        for key, val in (("ui_enabled", "false"), ("auto_watch", "false"), ("watcher_enabled", "false")):
            sh([str(CBM), "config", "set", key, val], env=env)
        t0 = time.time()
        r = sh([str(CBM), "cli", "--quiet", "index_repository", "--repo-path", str(w)], env=env, timeout=1800)
        info["index_seconds"], info["index_rc"] = round(time.time() - t0, 1), r.returncode
        info["index_out"] = re.sub(r"level=\w+ msg=\S+( \S+=\S+)*\n?", "", r.stdout + r.stderr)[-500:]
        sh(["pkill", "-u", str(os.getuid()), "-f", f"--cbm-daemon-internal.*{run_dir}"], env=env)
        (w / ".claude").mkdir(exist_ok=True)
        for sub in ("agents", "skills", "hooks"):
            shutil.copytree(CBM_TEMPLATE / ".claude" / sub, w / ".claude" / sub, dirs_exist_ok=True)
        shutil.copy(CBM_TEMPLATE / ".claude" / "settings.json", w / ".claude" / "settings.json")
        shutil.copy(CBM_TEMPLATE / ".mcp.json", w / ".mcp.json")
    info["arm_files"] = sorted(touched(w))                 # created by the arm's setup: not part of the agent's change
    return w, info


def wire_guardrail(w: Path, run_dir: Path) -> bool:
    """Add the 0.2.15 grep hook to the settings `devkb init --claude-hook` wrote, as this repository's own settings register it."""
    home = run_dir / "home"
    (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    py = DEVKB_BIN / "python"
    f = w / ".claude" / "settings.json"
    cfg = json.loads(f.read_text()) if f.exists() else {}
    hooks = cfg.setdefault("hooks", {})
    cmd = lambda script: f'env HOME="{home}" "{py}" "{GUARDRAIL / script}" 2>/dev/null || true'  # noqa: E731
    hooks.setdefault("PreToolUse", []).append({"matcher": "Read|Grep|Bash", "hooks": [{"type": "command", "command": cmd("devkb_guardrail.py"), "timeout": 20}]})
    hooks.setdefault("PostToolUse", []).append({"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": cmd("devkb_guardrail_post.py"), "timeout": 20}]})
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(cfg, indent=2))
    return GUARDRAIL.joinpath("devkb_guardrail.py").exists() and GUARDRAIL.joinpath("devkb_guardrail_post.py").exists()


def guardrail_summary(run_dir: Path) -> dict:
    """What the grep hook decided in this run, from its own log: decisions by action and reason, characters of answers it put in the context."""
    log = run_dir / "home" / ".claude" / "hooks" / "devkb-guardrail.log"
    acts: dict[str, int] = {}
    reasons: dict[str, int] = {}
    chars = n = 0
    try:
        for line in log.read_text().splitlines():
            if line.startswith("{"):
                d = json.loads(line)
                n += 1
                acts[d.get("action", "?")] = acts.get(d.get("action", "?"), 0) + 1
                key = f"{d.get('action')}:{d.get('reason')}"
                reasons[key] = reasons.get(key, 0) + 1
                chars += d.get("chars") or 0
    except (OSError, ValueError):
        pass
    return {"decisions": n, "by_action": acts, "by_reason": reasons, "answer_chars": chars}


def mcp_config(arm: str, w: Path, run_dir: Path) -> str:
    if arm == "none":
        p = run_dir / "no-mcp.json"
        p.write_text(json.dumps({"mcpServers": {}}))
        return str(p)
    return str(w / ".mcp.json")


def sandbox_settings(box: Path) -> dict:
    """What no agent may write: the clone's shared `.git` (refs, stash and objects every checkout uses). What it may neither read nor write: the
    hidden checks and task files, other runs' records, and the user's keys."""
    hidden = [RUN / "hidden", RUN / "tasks", OUT, Path.home() / ".ssh"]
    return isolation.settings(box, [ZSRC / ".git", *hidden], hidden)


def claude_cmd(prompt: str, arm: str, mcp: str, max_turns: str, box: Path) -> list[str]:
    allow = list(ALLOW) + ({"devkb": ["mcp__devkb"], "cbm": ["mcp__codebase-memory-mcp"]}.get(arm, []))
    return ["claude", "-p", prompt, "--model", MODEL, "--setting-sources", "project,local", "--output-format", "stream-json", "--verbose",
            "--max-turns", max_turns, "--permission-mode", "acceptEdits", "--strict-mcp-config", "--mcp-config", mcp,
            "--allowedTools", *allow, "--disallowedTools", *DENY, "--include-hook-events", "--settings", json.dumps(sandbox_settings(box))]


def entry_problems(arm: str, m: dict, info: dict | None = None) -> list[str]:
    """What the run really had against what the arm is: tools listed and hooks seen (the 0.2.15 lesson: a run is only worth scoring if it had its arm)."""
    p = []
    if m["tools_listed"] == 0:
        p.append("no init event: the tool list could not be read")
    if arm == "none" and m["graph_tools_listed"]:
        p.append("arm none had graph tools")
    if arm == "devkb" and info is not None and not info.get("guardrail_wired"):
        p.append("arm devkb: the grep hook is not wired")
    if arm in ("devkb", "cbm") and not m["graph_tools_listed"]:
        p.append(f"arm {arm} had no graph tool in its tool list")
    return p


def run_agent(w: Path, arm: str, prompt: str, run_dir: Path, max_turns: str = MAX_TURNS) -> tuple[object, float]:
    box = isolation.scratch(run_dir)
    shutil.rmtree(box, ignore_errors=True)
    for d in ("tmp", "cache"):
        (box / d).mkdir(parents=True)
    env = isolation.agent_env(env_for(arm, w, run_dir), box)
    cmd = claude_cmd(prompt, arm, mcp_config(arm, w, run_dir), max_turns, box)
    t0 = time.time()
    with open(run_dir / "stream.jsonl", "w") as fo, open(run_dir / "stderr.log", "w") as fe:
        try:
            code: object = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=RUN_TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    if arm == "cbm":
        sh(["pkill", "-u", str(os.getuid()), "-f", f"--cbm-daemon-internal.*{run_dir}"])
    shutil.rmtree(box, ignore_errors=True)
    return code, round(time.time() - t0, 1)


def agent_change(w: Path, t: dict, arm_files: list[str]) -> dict:
    """The agent's source change: files and lines, apart from the arm's own files, builds and tests (kept as a diff, scored by the hidden check)."""
    skip = [":(exclude)build", ":(exclude)hbuild", ":(exclude).devkb", ":(exclude).claude", ":(exclude).mcp.json"] + [f":(exclude){f}" for f in arm_files]
    sh(["git", "-C", str(w), "add", "-A", "--", ".", *skip])
    diff = sh(["git", "-C", str(w), "diff", "--cached", "HEAD", "--", "."]).stdout
    names = [n for n in sh(["git", "-C", str(w), "diff", "--cached", "--name-only", "HEAD"]).stdout.split("\n") if n]
    src = [n for n in names if not n.startswith("tests/")]
    ref = set(t.get("src_files") or [])
    stat = sh(["git", "-C", str(w), "diff", "--cached", "--numstat", "HEAD", "--", *[n for n in src]]).stdout
    lines = sum(int(a) + int(b) for a, b, _ in (x.split("\t") for x in stat.splitlines() if x.count("\t") == 2) if a.isdigit() and b.isdigit())
    hit = ref & set(src)
    return {"diff": diff, "files_changed": src, "tests_changed": [n for n in names if n.startswith("tests/")], "source_lines": lines,
            "ref_files": sorted(ref), "ref_recall": round(len(hit) / len(ref), 3) if ref else None,
            "precision": round(len(hit) / len(src), 3) if src and ref else None}


def hidden_check(w: Path, t: dict, run_dir: Path) -> dict:
    """The hidden test on the agent's tree: its own changes under the test directory are set aside first, then the check is installed and run."""
    pr, td = t["pr"], t["test_dir"]
    sh(["git", "-C", str(w), "checkout", t["base"], "--", td])
    sh(["git", "-C", str(w), "clean", "-fdq", "--", td])
    hid = RUN / "hidden" / pr
    if (hid / "apply.py").exists():
        r = sh([sys.executable, str(hid / "apply.py"), str(w)])
    else:
        r = sh(["git", "-C", str(w), "apply", str(hid / "tests.patch")])
    if r.returncode:
        return {"installed": False, "error": (r.stdout + r.stderr)[-300:]}
    env = env_for("none", w, run_dir)
    b = w / "hbuild"
    shutil.rmtree(b, ignore_errors=True)
    log = run_dir / "hidden.log"
    cfg = sh(["cmake", "-GNinja", "-DBOARD=native_sim/native/64", f"-DPython3_EXECUTABLE={RUN / 'zephyr-venv' / 'bin' / 'python'}", "-S", str(w / td), "-B", str(b)],
             env=env)
    bld = sh(["ninja", "-C", str(b)], env=env) if cfg.returncode == 0 else cfg
    log.write_text((cfg.stdout + cfg.stderr)[-3000:] + (bld.stdout + bld.stderr)[-6000:])
    if cfg.returncode or bld.returncode:
        return {"installed": True, "built": False, "passed": False, "error": "build failed: " + (bld.stdout + bld.stderr)[-300:]}
    try:
        r = subprocess.run([str(b / "zephyr" / "zephyr.exe")], capture_output=True, text=True, timeout=600, env=env)
        out, rc = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "", "timeout"
    with open(log, "a") as f:
        f.write("\n--- run ---\n" + out[-8000:])
    failed = re.findall(r"^\s*FAIL - (\S+)", out, re.M)
    return {"installed": True, "built": True, "rc": rc, "passed": rc == 0 and not failed, "tests_pass": len(re.findall(r"^\s*PASS - ", out, re.M)),
            "tests_fail": len(failed), "failed": failed[:8]}


def record(tag: str, **kw) -> dict:
    rec = dict(kw, tag=tag)
    (OUT / tag).mkdir(parents=True, exist_ok=True)
    (OUT / tag / "record.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def run(pr: str, arm: str, rep: int) -> dict:
    """One run. The cbm arm holds a machine-wide lock for the whole run: cbm keeps one daemon per user and refuses a second one started with another
    cache directory ("a different install"), so parallel cbm runs fail their index and arrive with no graph tools."""
    if arm == "cbm":
        import fcntl
        OUT.mkdir(parents=True, exist_ok=True)
        with open(RUN / "cbm.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return _run(pr, arm, rep)
    return _run(pr, arm, rep)


def _run(pr: str, arm: str, rep: int) -> dict:
    assert arm in ARMS, arm
    t = task(pr)
    tag = f"z{pr}-{arm}-r{rep}"
    run_dir = OUT / tag
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    w, info = prepare(t, arm, tag, run_dir)
    prompt = PROMPT.format(test_dir=t["test_dir"], issue=issue_text(pr))
    (run_dir / "prompt.txt").write_text(prompt)
    code, secs = run_agent(w, arm, prompt, run_dir)
    m = metrics.parse(run_dir / "stream.jsonl")
    change = agent_change(w, t, info["arm_files"])
    (run_dir / "agent.diff").write_text(change.pop("diff"))
    hidden = hidden_check(w, t, run_dir)
    rec = record(tag, task=pr, arm=arm, rep=rep, exit=code, seconds=secs, model=MODEL, base=t["base"], setup=info, metrics=m, change=change,
                 hidden=hidden, entry_problems=entry_problems(arm, m, info), guardrail=guardrail_summary(run_dir), prompt_sha256=__import__("hashlib").sha256(prompt.encode()).hexdigest())
    sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])
    return rec


def smoke(arm: str) -> dict:
    """One cheap question, to see the arm works before any batch: its tools are listed, a graph tool is used or not, the answer is right."""
    pr = "122187"
    t = task(pr)
    tag = f"smoke-{arm}"
    run_dir = OUT / tag
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    w, info = prepare(t, arm, tag, run_dir)
    code, secs = run_agent(w, arm, SMOKE_PROMPT, run_dir, max_turns="25")
    m = metrics.parse(run_dir / "stream.jsonl")
    text = ""
    for e in metrics.read(run_dir / "stream.jsonl"):
        if e.get("type") == "result":
            text = e.get("result") or ""
    ok = {k: v in text for k, v in SMOKE_EXPECT.items()}
    rec = record(tag, task=pr, arm=arm, exit=code, seconds=secs, setup=info, metrics=m, answer=text[-600:], answer_ok=ok, entry_problems=entry_problems(arm, m, info), guardrail=guardrail_summary(run_dir))
    sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])
    return rec


PROBE_BASE_TASK = "122187"      # base commit 3c410f0dfe8
PROBE_QUESTIONS = [            # (question, git-grep truth: (args, how the expected tokens are made))
    ("Q1: In which file and at which line is the function `tcp_options_check` defined?", ["-n", "-w", "tcp_options_check", "--", "subsys/net/ip/tcp.c"], "def"),
    ("Q2: Which functions call `tcp_options_check`?", None, "tcp_in"),
    ("Q3: In which .c file is `net_if_ipv4_addr_add` implemented?", None, "subsys/net/ip/net_if.c"),
    ("Q4: Which .c files under subsys/net/ call `net_if_ipv4_addr_add`? List the file paths.", ["-l", "-w", "net_if_ipv4_addr_add", "--", "subsys/net/*.c"], "files"),
    ("Q5: Which .c files under subsys/net/ and tests/net/ use `net_ipv4_is_addr_bcast`? List the file paths.", ["-l", "-w", "net_ipv4_is_addr_bcast", "--", "subsys/net/*.c", "tests/net/*.c"], "files"),
    ("Q6: Which .c files under subsys/net/ include the header `ipv4.h`? List the file paths.", ["-l", "ipv4.h", "--", "subsys/net/*.c"], "files"),
]


def probe_truth(w: Path) -> list[list[str]]:
    out = []
    for q, args, kind in PROBE_QUESTIONS:
        if args is None:
            out.append([kind])
            continue
        lines = sh(["git", "-C", str(w), "grep", *args]).stdout.splitlines()
        out.append(["tcp.c", "1165"] if kind == "def" else sorted({x.strip() for x in lines if x.strip()}))
    return out


def probe(arm: str, rep: int) -> dict:
    """Structural questions of the kind a code graph is built for (where is X defined, who calls X, which files use X), several in one session, on
    the base commit of the first task. It tests whether the agent chooses the graph tools when the question fits them, which the issue-driven tasks
    cannot show (their issues name the function, so the agent greps). Scored by the share of expected file paths or tokens in the answer."""
    import fcntl
    t = task(PROBE_BASE_TASK)
    tag = f"probe-{arm}-r{rep}"
    lock = open(RUN / "cbm.lock", "w") if arm == "cbm" else None
    if lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
    run_dir = OUT / tag
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    w, info = prepare(t, arm, tag, run_dir)
    truth = probe_truth(w)
    prompt = ("In this Zephyr checkout, answer each question below. Do not edit any file. Answer in the form `Q<n>: <answer>`, one line per question, "
              "with full file paths from the repository root.\n\n" + "\n".join(q for q, _, _ in PROBE_QUESTIONS))
    (run_dir / "prompt.txt").write_text(prompt)
    code, secs = run_agent(w, arm, prompt, run_dir, max_turns="60")
    m = metrics.parse(run_dir / "stream.jsonl")
    text = next((e.get("result") or "" for e in metrics.read(run_dir / "stream.jsonl") if e.get("type") == "result"), "")
    scores = []
    for (q, _, _), exp in zip(PROBE_QUESTIONS, truth):
        line = next((x for x in text.splitlines() if x.strip().startswith(q.split(":")[0] + ":")), "")
        body = "\n".join(text.split(q.split(":")[0] + ":", 1)[1].split("\nQ", 1)[:1]) if q.split(":")[0] + ":" in text else line
        exp = exp[:12]
        scores.append(round(sum(1 for e in exp if e in body) / len(exp), 3) if exp else None)
    rec = record(tag, task=PROBE_BASE_TASK, arm=arm, rep=rep, exit=code, seconds=secs, setup=info, metrics=m, answer=text[-1500:], expected=truth, scores=scores,
                 recall=round(sum(x for x in scores if x is not None) / max(1, len([x for x in scores if x is not None])), 3),
                 entry_problems=entry_problems(arm, m, info), guardrail=guardrail_summary(run_dir))
    sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])
    return rec


ISOLATION_SCRIPT = """#!/usr/bin/env bash
# Each line tries one thing; the harness checks the files from outside. Only files made for this test are touched.
r=isolation-results.txt; : > "$r"
echo own > own-file && echo "own_write ok" >> "$r"
echo tmp > "$TMPDIR/own-tmp" && echo "tmp_write ok" >> "$r"
{targets}
cat '{secret}' >/dev/null 2>&1 && echo "hidden_read ok" >> "$r" || echo "hidden_read blocked" >> "$r"
python3 - >> "$r" <<'PY'
import glob, os, socket
paths = ["/var/run/docker.sock", "/run/docker.sock", f"/run/user/{{os.getuid()}}/bus", "{probe_socket}"] + glob.glob("/tmp/tmux-*/*")
reached = []
for p in paths:
    try:
        s = socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect(p); reached.append(p)
    except OSError:
        pass
print("host_sockets", "reached " + " ".join(reached) if reached else "blocked")
PY
git status --short >/dev/null 2>&1 && echo "git_status ok" >> "$r" || echo "git_status failed" >> "$r"
cmake -GNinja -DBOARD=native_sim/native/64 -S samples/hello_world -B build-iso >build-iso.log 2>&1 && ninja -C build-iso >>build-iso.log 2>&1 \\
  && timeout 20 ./build-iso/zephyr/zephyr.exe -stop_at=1 2>&1 | grep -q "Hello World" && echo "zephyr_build ok" >> "$r" || echo "zephyr_build failed" >> "$r"
"""


def isolation_check() -> dict:
    """Canary files outside the run, an agent told to overwrite and delete them (shell and Write tool), and a look from outside afterwards."""
    t = task(PROBE_BASE_TASK)
    tag = "isolation"
    run_dir = OUT / tag
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    w, info = prepare(t, "none", tag, run_dir)
    mark = f"zbench-canary-{os.getpid()}"
    canaries = {"home": Path.home() / f".{mark}", "system_tmp": Path("/tmp") / mark, "shared_git": ZSRC / ".git" / mark,
                "other_run": isolation.scratch_root() / "_other-run" / mark, "records": OUT / mark, "sibling_checkout": WORK / "_sibling" / mark,
                "write_tool": Path.home() / f".{mark}-write"}
    secret = RUN / "hidden" / mark
    for p in (*canaries.values(), secret):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("intact\n")
    targets = "\n".join(f"echo changed > '{p}' 2>/dev/null; rm -f -- '{p}' 2>/dev/null; echo '{k} tried' >> \"$r\""
                        for k, p in canaries.items() if k != "write_tool")
    probe = Path("/tmp") / f"{mark}.sock"                   # a listener of our own: what any host socket would be to the agent
    probe.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(probe))
    listener.listen(1)
    (w / "isolation_check.sh").write_text(ISOLATION_SCRIPT.format(targets=targets, secret=secret, probe_socket=probe))
    prompt = ("This checkout tests a sandbox; every file named is a throwaway made for the test. Do both, then report what each printed or returned:\n"
              "1. Run `bash isolation_check.sh` (allow it several minutes).\n"
              f"2. Use the Write tool to write the word `changed` to `{canaries['write_tool']}`. If it is refused, do not try another way.")
    try:
        code, secs = run_agent(w, "none", prompt, run_dir, max_turns="12")
        results = dict(x.split(" ", 1) for x in (w / "isolation-results.txt").read_text().splitlines() if " " in x) if (w / "isolation-results.txt").exists() else {}
        checks = {f"{k} untouched": p.exists() and p.read_text() == "intact\n" for k, p in canaries.items()}
        checks.update({f"{k} tried": results.get(k) == "tried" for k in canaries if k != "write_tool"})
        checks.update({"own folder writable": results.get("own_write") == "ok", "own temp writable": results.get("tmp_write") == "ok",
                       "hidden checks unreadable": results.get("hidden_read") == "blocked", "git status works": results.get("git_status") == "ok",
                       "zephyr builds and runs": results.get("zephyr_build") == "ok", "host sockets unreachable": results.get("host_sockets") == "blocked"})
        used = metrics.parse(run_dir / "stream.jsonl")["calls_by_name"]
        checks["write tool tried"] = used.get("Write", 0) > 0
        log = (w / "build-iso.log").read_text()[-1500:] if (w / "build-iso.log").exists() else ""
    finally:
        listener.close()
        for p in (*canaries.values(), secret, probe):
            p.unlink(missing_ok=True)
        for d in (canaries["other_run"].parent, canaries["sibling_checkout"].parent):      # folders made only for the canaries
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    rec = record(tag, exit=code, seconds=secs, passed=bool(checks) and all(checks.values()) and code == 0, checks=checks, results=results,
                 calls=used, build_log=log, claude=sh(["claude", "--version"]).stdout.strip())
    sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])
    return rec


def check(pr: str) -> None:
    """The hidden check on the base commit and on the fix commit, with no agent: fails on the base, passes on the fix."""
    t = task(pr)
    for state, rev in (("base", t["base"]), ("fix", t["fix"])):
        tag = f"check-{pr}-{state}"
        run_dir = OUT / tag
        run_dir.mkdir(parents=True, exist_ok=True)
        w, _ = prepare(t, "none", tag, run_dir, base=rev)
        print(pr, state, json.dumps(hidden_check(w, t, run_dir)))
        sh(["git", "-C", str(ZSRC), "worktree", "remove", "--force", str(w)])


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"] and len(a) == 4:
        r = run(a[1], a[2], int(a[3]))
        print(json.dumps({k: r[k] for k in ("tag", "exit", "seconds", "hidden", "entry_problems")}, default=str))
    elif a[:1] == ["smoke"] and len(a) == 2:
        r = smoke(a[1])
        print(json.dumps({k: r[k] for k in ("tag", "exit", "seconds", "answer_ok", "entry_problems")}, default=str))
    elif a[:1] == ["probe"] and len(a) == 3:
        r = probe(a[1], int(a[2]))
        print(json.dumps({k: r[k] for k in ("tag", "exit", "seconds", "scores", "recall", "entry_problems")}, default=str), r["metrics"]["graph_calls"], "graph calls")
    elif a == ["isolation"]:
        r = isolation_check()
        print(json.dumps({k: r[k] for k in ("passed", "exit", "seconds", "checks")}, indent=1))
        sys.exit(0 if r["passed"] else 1)
    elif a[:1] == ["check"] and len(a) == 2:
        check(a[1])
    else:
        print(__doc__)
        sys.exit(2)
