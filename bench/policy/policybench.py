"""#126 before/after: does the devkb-repo policy + guardrail change how an agent implements a devkb fix?

  python policybench.py run ISSUE[,ISSUE...] [--reps 3] [--parallel 2]
  python policybench.py score ISSUE[,ISSUE...]     re-scores every run of each ISSUE with today's hidden check and
                                                   writes results-ISSUE.jsonl (the input of release_table.py)

before: origin/main as it is (no AGENTS.md/CLAUDE.md/.mcp.json, no graph), guardrail off. devkb is on PATH, as on
        this machine.
after:  the #126 branch (policy in AGENTS.md, CLAUDE.md import, .mcp.json lean-pack, .claude/settings.json guardrail),
        graphs built for the checkout and the corpus, guardrail on.
Both: the C/C++ corpus copied in with its .git, the issue as filed, Sonnet, same caps. Scored by accept/<issue>.py.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import storybench as sb
import toolenv

B = sb.B
BASES = {"before": "origin/main", "after": "ce284c4", "after2": os.environ.get("POLICY_BRANCH", "chore/126-devkb-first-on-devkb"),
         "cli": os.environ.get("POLICY_BRANCH", "chore/126-devkb-first-on-devkb"),   # after2 without the MCP server
         "none": "origin/main",                                   # main with every devkb trace removed, devkb denied
         "cli130": "feat/130-guardrail-enforce",                  # CLI-only, enforcing guardrail (#130)
         "climain": "origin/main",                                # main as merged (#129): CLI-only policy, reminder guardrail
         "nonekeep": "origin/main",                               # no devkb, but the devkb files kept (the guardrail is the code being changed)
         "release": "origin/main",                                # tri mode (#225): main's code, the last release's devkb
         "main": "origin/main",                                   # tri mode (#225): main's code, main's devkb
         "noteach": "origin/main",                                # main's devkb with D1 off (DEVKB_GUARDRAIL_TEACH=0, #267)
         "outline": "origin/main"}                                # #218 D2: main's devkb, outline on first open
# Tri-mode arms take their devkb (CLI, graph build, hook) from a tool environment built from an exact commit, never
# from the checkout the agent edits (#225). POLICY_RELEASE / POLICY_MAIN override the refs.
ENV_REF = {"release": lambda: os.environ.get("POLICY_RELEASE") or toolenv.latest_release(),
           "main": lambda: os.environ.get("POLICY_MAIN") or "origin/main",
           "noteach": lambda: os.environ.get("POLICY_MAIN") or "origin/main",
           "outline": lambda: os.environ.get("POLICY_MAIN") or "origin/main"}
# Every devkb arm keeps the answers its agents were given (#218); D1 and D2 are the two direct-path candidates.
ARM_ENV = {"release": {"DEVKB_GUARDRAIL_KEEP": "1"}, "main": {"DEVKB_GUARDRAIL_KEEP": "1"},
           "noteach": {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_TEACH": "0"},   # main without D1 (on by default, #267)
           "outline": {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_OUTLINE": "1"}}
HIDDEN = ("bench/policy/accept",)                               # the hidden checks: never in an agent's checkout (#223)
GROUPS = json.loads((Path(__file__).resolve().parent / "groups.json").read_text())   # tickets done as one job
# after2 (the revised #126 + #127): navigation through the branch's own devkb, which records every query
TOOL = {"after2": str(B / "toolenv-126" / "bin" / "devkb"), "cli": str(B / "toolenv-126" / "bin" / "devkb"),
        "cli130": str(B / "toolenv-126" / "bin" / "devkb"), "climain": str(B / "toolenv-126" / "bin" / "devkb")}
TRACE = ("AGENTS.md", "CLAUDE.md", ".claude", ".mcp.json", "scripts/devkb_guardrail.py",
         "tests/test_devkb_guardrail.py")   # and the tests of what is removed, so the suite starts green
PROMPT = """You are working in a clone of devkb (a code-graph tool for coding agents; Python; its venv is .venv, run
Python as .venv/bin/python). The pinned C/C++ corpus repositories are in ./corpus/ (cJSON, leveldb, fmt), each its own
git repository. Fix the issue below: change the code, add a regression test that fails before your fix and passes
after it, keep the whole test suite passing (.venv/bin/python -m pytest -q), and commit your work with git. Do not
push and do not use gh.

# {title}

{body}
"""


_DATA_PATH = re.compile(r"bench/results/[\w.\-/]+")
_FENCE = re.compile(r"```.*?```", re.S)


def without_missing_data(body: str, w: Path) -> str:
    """A ticket's fenced reproduction blocks that use data under bench/results/ which is not in the checkout are replaced by
    one line saying so (#336). Without it every agent tried the missing path (2.0 to 3.4 calls per run) and reported that
    it could not run the reproduction. Blocks that name nothing missing, and all other text, stay as filed."""
    def swap(m):
        gone = [p for p in _DATA_PATH.findall(m.group(0)) if not (w / p.rstrip("/")).exists()]
        if not gone:
            return m.group(0)
        return (f"(Reproduction command omitted: the data it uses, {gone[0]}, is not in this checkout. "
                "The regression test you write is the check.)")
    return _FENCE.sub(swap, body)


def checkout(w: Path, arm: str):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(sb.REPO), "archive", BASES[arm]], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(w)], input=tar, check=True)
    for h in HIDDEN:
        shutil.rmtree(w / h, ignore_errors=True)
    env = toolenv.build(ENV_REF[arm]()) if arm in ENV_REF else None
    for r in sb.CORPUS_REPOS:
        shutil.copytree(sb.CORPUS / r, w / "corpus" / r, ignore=shutil.ignore_patterns(".devkb"), symlinks=True)
    spec = w / "docs" / "specs" / "SPEC-DKB-004_cpp-supported.md"     # the story's spec (PR #125, not merged yet)
    if not spec.exists():
        spec.write_text(sb.sh(["git", "-C", str(sb.REPO), "show", "spec/dkb-004-cpp-supported:docs/specs/SPEC-DKB-004_cpp-supported.md"]).stdout)
    if arm == "none":                                # no devkb trace at all (nonekeep: files kept, devkb denied, no graph)
        for t in TRACE:
            p = w / t
            shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
        for t in (w / "scripts").glob("devkb_guardrail*.py"):    # the guardrail's scripts go with it
            t.unlink(missing_ok=True)
    if arm != "nonekeep" and (arm == "none" or os.environ.get("POLICY_EQUAL_SUITE", "1") == "1"):
        trim_tests(w)                                 # every arm runs the same suite as `none` (#331); nonekeep keeps all
    if env:                                           # the arm's hook runs the tool environment's guardrail
        st_path = w / ".claude" / "settings.json"
        st = json.loads(st_path.read_text()) if st_path.exists() else {}
        st["hooks"] = toolenv.hooks_settings(env)
        st_path.parent.mkdir(exist_ok=True)
        st_path.write_text(json.dumps(st, indent=2) + "\n")
    gi = w / ".gitignore"
    gi.write_text(gi.read_text() + "\ncorpus/\n")
    sb.sh(["git", "init", "-q"], cwd=w)
    for c in (["add", "-A"], ["-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", f"devkb ({arm})"]):
        sb.sh(["git", *c], cwd=w)
    sb.sh(["uv", "venv", "-q", ".venv"], cwd=w)
    sb.sh(["uv", "pip", "install", "-q", "--python", ".venv/bin/python", "-e", ".[dev]", "libclang"], cwd=w)
    if arm not in ("before", "none", "nonekeep"):                              # what a session in a #126 checkout has: graphs for repo and corpus
        for p in [w, *(w / "corpus" / r for r in sb.CORPUS_REPOS)]:
            subprocess.run([tool_of(arm, env), "build", "--project", str(p)], capture_output=True)
        sb.check_graphs(w)
    if os.environ.get("POLICY_PREREGISTER_POST") == "1" and (w / ".claude" / "settings.json").exists():
        # Claude Code refuses headless writes to .claude/settings.json (verified 2026-11-18), so a ticket that needs a
        # new hook cannot be done by an agent: register the PostToolUse script it is asked to write, and give the
        # PreToolUse hook time to run devkb.
        st = json.loads((w / ".claude" / "settings.json").read_text())
        for m in st["hooks"].get("PreToolUse", []):
            for h in m["hooks"]:
                h["timeout"] = 20
        st["hooks"]["PostToolUse"] = [{"matcher": "Grep|Bash", "hooks": [{"type": "command", "timeout": 20, "command":
            '[ -f "$CLAUDE_PROJECT_DIR/scripts/devkb_guardrail_post.py" ] && python3 "$CLAUDE_PROJECT_DIR/scripts/devkb_guardrail_post.py" 2>/dev/null || true'}]}]
        (w / ".claude" / "settings.json").write_text(json.dumps(st, indent=2) + "\n")
        sb.sh(["git", "add", "-A"], cwd=w)
        sb.sh(["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "register the PostToolUse hook"], cwd=w)
    base_suite = subprocess.run([str(w / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"], cwd=w,
                                capture_output=True, text=True, timeout=1800)
    failed = [l.split(" - ")[0] for l in base_suite.stdout.splitlines() if l.startswith(("FAILED ", "ERROR "))]
    n_tests = collected(subprocess.run([str(w / ".venv/bin/python"), "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                                       cwd=w, capture_output=True, text=True, timeout=600).stdout)
    meta = {"arm": arm, "tests_collected": n_tests, "base_suite": (base_suite.stdout.strip().splitlines() or [""])[-1], "base_failed": failed[:5],
            "base_green": base_suite.returncode == 0,
            "devkb_commit": env["commit"] if env else None, "hook_sha": env["hook_sha"] if env else None}
    (w / ".bench-arm.json").write_text(json.dumps(meta) + "\n")
    (w / ".bench-base").write_text(sb.sh(["git", "rev-parse", "HEAD"], cwd=w).stdout.strip())
    if not meta["base_green"]:                        # a red base would be counted against the agent (#221)
        raise RuntimeError(f"{w.name}: the checkout's own suite is red before the agent starts: {meta['base_suite']} {failed[:3]}")


def trim_tests(w: Path) -> None:
    """Remove every test that exercises the guardrail's scripts, and every test module that imports one that is gone, so
    the suite starts green in the arm that has no guardrail, and is the same suite in every other arm (#331): a cost,
    turn or wall-time difference then does not include the suite's size. POLICY_EQUAL_SUITE=0 keeps the other arms' tests
    (for a ticket about the guardrail itself; use the nonekeep arm as its control)."""
    for t in (w / "tests").glob("*.py"):
        if "devkb_guardrail" in t.read_text(errors="replace"):
            t.unlink(missing_ok=True)
    remove_dependents(w / "tests")


def collected(out: str) -> int | None:
    """The number of tests in `pytest --collect-only -q` output (its last line: 'N tests collected in …'), else None."""
    m = re.search(r"(\d+) tests? collected", (out or "").strip().splitlines()[-1] if (out or "").strip() else "")
    return int(m.group(1)) if m else None


def remove_dependents(tests: Path) -> None:
    """Remove every test module that imports one that is gone, until none does (#221)."""
    while True:
        have = {p.stem for p in tests.glob("*.py")}
        gone = []
        for p in tests.glob("*.py"):
            text = p.read_text(errors="replace")
            mods = set(re.findall(r"^\s*(?:from|import)\s+(test_\w+)", text, re.M))
            if any(m not in have for m in mods):
                gone.append(p)
        if not gone:
            return
        for p in gone:
            p.unlink()


def tool_of(arm: str, env: dict | None) -> str:
    return env["bin"] if env else TOOL.get(arm, sb.DEVKB)


# Only the checkout's settings: never the machine's user-level hooks, which would run beside the arm's own (#225).
SOURCES = ["--setting-sources", "project,local"]

SETTINGS_NOTE = """

Environment note: `.claude/settings.json` cannot be edited in this environment (Claude Code refuses it). It already
registers `scripts/devkb_guardrail.py` as the PreToolUse hook and `scripts/devkb_guardrail_post.py` (create it) as the
PostToolUse hook for Grep and Bash, each with a 20-second timeout. Do not try to change the settings file."""


HARNESS_REPO = Path(__file__).resolve().parents[2]          # the repository that holds this harness, its hidden checks and results
CACHE = Path.home() / ".cache" / "devkb"


def work_dir() -> Path:
    """Where each run's checkout is made: outside the harness repository (#340). Inside it, an agent's working directory
    contains the repository's own path, and a cut-down absolute path reached the harness's source (3 of 48 runs wrote to it)."""
    return Path(os.environ.get("POLICY_WORK_DIR") or CACHE / "policy-work")


def harness_state(repo: Path | None = None) -> str:
    """HEAD and the uncommitted changes of the harness repository, apart from the files the harness itself writes (results,
    the empty MCP config). A change between two calls is a write by someone else: an agent's stray edit (#340)."""
    repo = repo or HARNESS_REPO
    def git(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout
    return git("rev-parse", "HEAD").strip() + "\n" + git("status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude)bench/policy/results-*",
                                                         ":(exclude)bench/policy/no-mcp.json")


TEMPLATES = Path(os.environ.get("POLICY_TEMPLATES_DIR") or CACHE / "policy-templates")   # outside the repository too (#340)


def template_for(arm: str) -> Path:
    """One prepared checkout per arm and base commit (files, corpus, venv, graphs, base suite checked), made once and
    copied for each run: the 4-5 minutes of setup a run used to repeat (POLICY_TEMPLATES=0 turns it off)."""
    base = sb.sh(["git", "-C", str(sb.REPO), "rev-parse", f"{BASES[arm]}^{{commit}}"]).stdout.strip()
    envc = toolenv.resolve(ENV_REF[arm]()) if arm in ENV_REF else "none"
    suite = "eq" if os.environ.get("POLICY_EQUAL_SUITE", "1") == "1" else "full"      # the suite is content: part of the key (#331)
    post = "-post" if os.environ.get("POLICY_PREREGISTER_POST") == "1" else ""      # it adds a hook to the checkout (#307)
    t = TEMPLATES / f"{arm}-{base[:12]}-{envc[:12]}-suite{suite}{post}"
    with toolenv.held(TEMPLATES / f".{t.name}.lock"):   # runs of one arm, in this or another benchmark process, wait
                                                        # for the same template: never built twice, never deleted in use
        if not (t / ".bench-ready").exists():
            if t.exists():
                shutil.rmtree(t)
            checkout(t, arm)                      # raises on a red base: then every run of this arm is refused
            (t / ".bench-ready").write_text(base + "\n")
    return t


def from_template(t: Path, w: Path) -> None:
    """Copy a prepared checkout and point its absolute paths (venv scripts, the editable install's finder, the graph
    files) at the copy, so the run's devkb is the code its agent edits, not the template's."""
    if w.exists():
        shutil.rmtree(w)
    w.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-a", "--reflink=auto", str(t), str(w)], check=True)
    (w / ".bench-ready").unlink(missing_ok=True)
    old, new = str(t), str(w)
    files = [*(w / ".venv" / "bin").glob("*"), *(w / ".venv").glob("lib/python*/site-packages/__editable__*"),
             *(w / ".venv").glob("lib/python*/site-packages/*.pth"), *(w / ".venv").glob("lib/python*/site-packages/*.dist-info/*"),
             w / ".venv" / "pyvenv.cfg", *w.glob(".devkb/*"), *w.glob("corpus/*/.devkb/*")]
    for f in files:
        if not f.is_file() or f.is_symlink() or f.stat().st_size > 200_000_000:
            continue
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if old.encode() in data:
            st = f.stat()
            f.write_bytes(data.replace(old.encode(), new.encode()))
            os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))   # keep mtimes: the graph's freshness checks compare them


def run_one(issue: str, arm: str, rep: int) -> str:
    """One run; any error after setup (a GitHub call that fails, a crashed agent wrapper) is recorded as the run's end,
    never raised into the batch loop, where it stopped every later progress line."""
    try:
        return _run_one(issue, arm, rep)
    except Exception as e:  # noqa: BLE001
        tag = f"p{issue}-{arm}-r{rep}"
        out = B / "runs" / tag
        out.mkdir(parents=True, exist_ok=True)
        if not (out / "end").exists():
            (out / "end").write_text(json.dumps({"exit": "error", "seconds": 0, "error": f"{type(e).__name__}: {e}"[-400:]}))
        return f"error {tag}: {type(e).__name__}: {e}"


def _run_one(issue: str, arm: str, rep: int) -> str:
    tag = f"p{issue}-{arm}-r{rep}"
    out = B / "runs" / tag
    if (out / "end").exists() and json.loads((out / "end").read_text()).get("exit") not in ("error", "base-red"):
        return f"skip {tag}"                          # an error, or a refused red base, is set up again (#305)
    out.mkdir(parents=True, exist_ok=True)
    w = work_dir() / tag
    try:
        if os.environ.get("POLICY_TEMPLATES", "1") == "1":
            from_template(template_for(arm), w)
        else:
            checkout(w, arm)
    except RuntimeError as e:                         # a red base (#221): recorded, not run or scored; set up again next batch (#305)
        (out / "end").write_text(json.dumps({"exit": "base-red", "seconds": 0, "error": str(e)[-400:]}))
        return f"refused {tag}: {e}"
    except Exception as e:  # noqa: BLE001  a setup that fails is recorded, never a run that silently disappears
        (out / "end").write_text(json.dumps({"exit": "error", "seconds": 0, "error": f"setup: {type(e).__name__}: {e}"[-400:]}))
        return f"error {tag}: setup failed: {e}"       # not a red base: run again in the next batch (#305)
    t = json.loads(sb.sh(["gh", "issue", "view", issue, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
    for extra in GROUPS.get(issue, []):            # tickets done as one job (same code): bench/policy/groups.json
        t2 = json.loads(sb.sh(["gh", "issue", "view", extra, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
        t = {"title": t["title"] + f" (with #{extra})", "body": t["body"] + f"\n\n# Same work: #{extra}, " + t2["title"] + "\n\n" + t2["body"]}
    if arm.startswith("after"):                      # "cli": no MCP server, devkb only through the shell
        mcp = str(w / ".mcp.json")
        cfg = json.loads(Path(mcp).read_text())
        cfg["mcpServers"]["devkb"]["command"] = TOOL.get(arm, sb.DEVKB)
        Path(mcp).write_text(json.dumps(cfg, indent=2) + "\n")
    else:
        mcp = str(B / "no-mcp.json")
        Path(mcp).write_text(json.dumps({"mcpServers": {}}))
    prompt = (sb.PROMPT if issue == "117" else PROMPT).format(title=t["title"], body=without_missing_data(t["body"], w))
    if os.environ.get("POLICY_PREREGISTER_POST") == "1":
        prompt += SETTINGS_NOTE
    deny = sb.DENY + (["Bash(devkb:*)", "Bash(.venv/bin/devkb:*)"] if arm in ("none", "nonekeep") else [])   # both forms (#335)
    meta = json.loads((w / ".bench-arm.json").read_text())
    env_bin = tool_of(arm, toolenv.build(ENV_REF[arm]()) if arm in ENV_REF else None)
    cmd = ["claude", "-p", prompt, "--model", sb.MODEL, *SOURCES, "--output-format",
           "stream-json", "--verbose", "--max-turns", "250" if issue in ("117", "131") else "150", "--permission-mode", "acceptEdits", "--strict-mcp-config",
           "--mcp-config", mcp, "--allowedTools", *sb.ALLOW, "--disallowedTools", *deny,
           "--include-hook-events"]                  # the stream then records what the hook said to the agent (#330)
    # The Bash tool backgrounds a command after 120 s by default; a full suite that runs about that long then costs the agent
    # extra turns to wait for it, in one arm and not the other (#334). Every arm gets the same, longer limit.
    limit = os.environ.get("POLICY_BASH_TIMEOUT_MS", "600000")
    env = dict(os.environ, BASH_DEFAULT_TIMEOUT_MS=limit, BASH_MAX_TIMEOUT_MS=limit,
               DEVKB_GUARDRAIL={"before": "0", "none": "0", "nonekeep": "0", "cli130": "enforce"}.get(arm, "1"),
               PATH=f"{Path(env_bin).parent}:{w / '.venv' / 'bin'}:{os.environ['PATH']}", **ARM_ENV.get(arm, {}))
    (out / "arm.json").write_text(json.dumps(meta) + "\n")
    t0 = time.time()
    before = harness_state()
    with open(out / "stream.jsonl", "w") as fo, open(out / "stderr.log", "w") as fe:
        try:
            code = subprocess.run(cmd, cwd=w, env=env, stdout=fo, stderr=fe, timeout=5400).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    after = harness_state()
    touched = sorted(set(after.splitlines()) ^ set(before.splitlines()))     # the lines that appeared or went away (#340)
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0), **({"contaminated": touched} if touched else {})}))
    try:                                              # scored now, while other agents run, not in a tail after the batch
        r = score_run(issue, out)
        if r:
            (out / "score.json").write_text(json.dumps(r) + "\n")
    except Exception as e:  # noqa: BLE001  `score` scores it later
        (out / "score-error.txt").write_text(str(e)[-2000:])
    return f"done {tag} exit={code} {round(time.time() - t0)}s" + (f" CONTAMINATED the harness repository: {touched}" if touched else "")


def _failed_ids(stdout: str) -> list[str]:
    """Test ids pytest -rfE reports as FAILED or ERROR (the summary lines), in order, without their messages."""
    ids = []
    for line in stdout.splitlines():
        if line.startswith(("FAILED ", "ERROR ")):
            tid = line.split(" ", 1)[1].split(" - ", 1)[0].strip()
            if tid and tid not in ids:
                ids.append(tid)
    return ids


def run_suite(w: Path, timeout: int = 1800) -> dict:
    """The checkout's full suite, with the ids of what failed. A red suite is run in full once more (#301): a failed
    test is flaky (load-sensitive, recorded, not held against the change) only when the whole suite passes the second
    time. A test that passes alone but fails again in the second full run is order-dependent, which is the change's
    failure, so the suite stays red. (#260 re-ran the failed tests alone, which let an order dependence pass as flaky.)"""
    py = str(w / ".venv/bin/python")
    cmd = [py, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"]
    t = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=timeout)
    last = (t.stdout.strip().splitlines() or [""])[-1]
    failed = _failed_ids(t.stdout)
    row = {"suite_pass": t.returncode == 0, "suite": last, "suite_failed": failed, "suite_flaky": []}
    if t.returncode == 0 or not failed:                 # green, or red with nothing to re-run (a crash): as it is
        return row
    r = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=timeout)
    if r.returncode == 0:                               # green on the second full run: the first failures were flaky
        row.update(suite_failed=[], suite_flaky=failed, suite_pass=True, suite_first=last)
        return row
    again = _failed_ids(r.stdout)
    still = [x for x in failed if x in again] or again or failed   # red twice: the ones that failed both times first
    row.update(suite_failed=still, suite_flaky=[], suite_pass=False, suite_first=last)
    return row


def score_run(issue: str, out: Path) -> dict | None:
    """One run's row: the full suite, the hidden check, the transcript. None for a refused run or a missing checkout."""
    _, arm, rep = out.name.split("-")
    w = work_dir() / out.name
    if not (w / ".bench-base").exists() or not (out / "end").exists():
        return None
    end = json.loads((out / "end").read_text())
    if end.get("exit") in ("base-red", "error"):
        return None
    base = (w / ".bench-base").read_text().strip()
    suite = run_suite(w)
    acc = B / "accept" / (f"{issue}-group.py" if (B / "accept" / f"{issue}-group.py").exists() else f"{issue}.py")
    arm_meta = json.loads((out / "arm.json").read_text()) if (out / "arm.json").exists() else {}
    a = subprocess.run([sys.executable, str(acc), str(w)], capture_output=True, text=True, timeout=1800)
    logs = [p for p in w.rglob("*.jsonl") if ".venv" not in p.parts and "corpus" not in p.parts
            and ".devkb" not in p.parts and p.stat().st_mtime > float(end.get("start", 0) or 0)
            and '"verdict"' in p.read_text(errors="replace")[:4000]]
    changed = sb.sh(["git", "diff", "--name-only", base], cwd=w).stdout.split()
    return {"run": out.name, "issue": issue, "arm": arm, "rep": rep, "exit": end["exit"],
            "seconds": end["seconds"], **suite,
            "acceptance": json.loads(a.stdout.strip().splitlines()[-1]) if a.stdout.strip() else {"error": a.stderr[-300:]},
            "dogfood_log": [str(p.relative_to(w)) for p in logs if str(p.relative_to(w)) in changed or
                            sb.sh(["git", "status", "--porcelain", str(p.relative_to(w))], cwd=w).stdout],
            "diff": sb.sh(["git", "diff", "--shortstat", base], cwd=w).stdout.strip(),
            "accept_sha256": hashlib.sha256(acc.read_bytes()).hexdigest(),          # which check scored it (#223)
            "base_green": arm_meta.get("base_green"), "base_suite": arm_meta.get("base_suite"),   # #221
            "tests_collected": arm_meta.get("tests_collected"),                                    # #331
            "contaminated": end.get("contaminated") or [],                                         # #340
            "devkb_commit": arm_meta.get("devkb_commit"), "hook_sha": arm_meta.get("hook_sha"),   # #225
            "telemetry": sum(len((d / ".devkb" / "process-api-telemetry.jsonl").read_text().splitlines())
                             for d in [w, *(w / "corpus" / r for r in sb.CORPUS_REPOS)]
                             if (d / ".devkb" / "process-api-telemetry.jsonl").exists()),
            **sb.transcript(out / "stream.jsonl")}


def score(issues):
    """Every run's row: the one saved when the run ended, unless its hidden check changed since (or POLICY_RESCORE=1)."""
    rows = []
    for issue in issues:
        only = set(filter(None, os.environ.get("POLICY_ARMS", "").split(",")))
        acc = B / "accept" / (f"{issue}-group.py" if (B / "accept" / f"{issue}-group.py").exists() else f"{issue}.py")
        sha = hashlib.sha256(acc.read_bytes()).hexdigest() if acc.exists() else ""
        for out in sorted((B / "runs").glob(f"p{issue}-*")):
            _, arm, rep = out.name.split("-")
            if only and arm not in only:
                continue
            ex = json.loads((out / "end").read_text()).get("exit") if (out / "end").exists() else None
            if ex in ("base-red", "error"):
                print(out.name, "REFUSED (red base, not scored)" if ex == "base-red" else "ERROR (not scored; run again)", flush=True)
                continue
            saved = json.loads((out / "score.json").read_text()) if (out / "score.json").exists() else None
            r = saved if saved and saved.get("accept_sha256") == sha and os.environ.get("POLICY_RESCORE") != "1" else score_run(issue, out)
            if not r:
                continue
            rows.append(r)
            print(r["run"], "pass" if r["acceptance"].get("pass") else "FAIL", "suite" if r["suite_pass"] else "SUITE-RED",
                  f"${r['cost']:.2f}", "devkb", r["devkb_queries"], "guard", r["guardrail_fired"], "log", r["dogfood_log"], flush=True)
    only = set(filter(None, os.environ.get("POLICY_ARMS", "").split(",")))
    scored = {r["run"] for r in rows}

    def other_arms(path):
        """The rows already in `path` of the arms POLICY_ARMS leaves out of this scoring: re-scoring one arm replaces only
        that arm's rows, and the release table keeps its baseline (#306)."""
        if not only or not path.exists():
            return []
        return [r for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip())
                if r.get("issue") in issues and r.get("arm") not in only and r.get("run") not in scored]
    keep_policy = other_arms(B / "results-policy.jsonl")
    keep_issue = {i: other_arms(B / f"results-{i}.jsonl") for i in issues}
    with open(B / "results-policy.jsonl", "w") as f:
        for r in keep_policy + rows:
            f.write(json.dumps(r) + "\n")
    for issue in issues:                              # one file per ticket, every run scored by today's check (#223)
        with open(B / f"results-{issue}.jsonl", "w") as f:
            for r in [x for x in keep_issue[issue] if x.get("issue") == issue] + [r for r in rows if r["issue"] == issue]:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    issues = a[1].split(",")
    if a[0] == "run":
        reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 3     # 3 by default: 2 cannot tell a change from noise (#222)
        par = int(a[a.index("--parallel") + 1]) if "--parallel" in a else 8    # the work is mostly waiting on the API
        arms = os.environ.get("POLICY_ARMS", "before,after").split(",")
        first = int(os.environ.get("POLICY_FIRST_REP", "1"))
        # one batch, one main: the arms' code and main's devkb are pinned to the commit main is at when the batch starts,
        # so a merge during the batch never splits its runs across two commits
        pinned = sb.sh(["git", "-C", str(sb.REPO), "rev-parse", "origin/main"]).stdout.strip()
        os.environ.setdefault("POLICY_MAIN", pinned)
        for k, v in BASES.items():
            if v == "origin/main":
                BASES[k] = os.environ["POLICY_MAIN"]
        print(f"batch pinned to main {os.environ['POLICY_MAIN'][:12]}", flush=True)
        jobs = [(i, arm, r) for i in issues for arm in arms for r in range(first, first + reps)]
        random.Random(126).shuffle(jobs)
        with cf.ThreadPoolExecutor(par) as ex:
            for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
                print(f.result(), flush=True)
    else:
        score(issues)
