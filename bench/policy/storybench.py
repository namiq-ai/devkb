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
import hashlib
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
{commands}
# {title}

{body}
"""
# The same for every arm, appended to both prompts (#369). Each clause answers a refusal reason the session gave in the
# runs (the tool_result of every refused call; docs/BENCHMARK.md, "Permission denials").
COMMANDS = """
How to run commands here (the session refuses other forms): run shell commands from the checkout root and do not `cd`
first (a `cd` followed by git, a redirect or a write is refused); stay inside the checkout, for scratch files too (no
`..`, `/tmp` or other directories); no shell variables or `NAME=value` prefixes, loops, `$(...)` or subshells;
call the venv as .venv/bin/python.
Create and change files with the Write and Edit tools, not with `sed -i`, heredocs or Python one-offs that write files:
code with braces and quotes in a shell command is refused. Pipes (`| tail -20`) and `;` between commands are fine.
"""
ALLOW = ["Read", "Edit", "Write", "Glob", "Grep", "TodoWrite", "mcp__devkb",
         "Bash(git:*)", "Bash(.venv/bin/python:*)", "Bash(.venv/bin/pytest:*)", "Bash(python3:*)", "Bash(devkb:*)", "Bash(.venv/bin/devkb:*)",
         "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(grep:*)",
         "Bash(rg:*)", "Bash(diff:*)", "Bash(sed -n:*)", "Bash(awk:*)", "Bash(sort:*)", "Bash(uniq:*)", "Bash(mkdir:*)",
         "Bash(make:*)", "Bash(cd:*)", "Bash(echo:*)", "Bash(jq:*)"]
DENY = ["Bash(git push:*)", "Bash(gh:*)", "Task", "WebFetch", "WebSearch"]


def story_prompt(t: dict) -> str:
    """The story bench's prompt for a ticket ({title, body}), with the command rules every arm gets (#369)."""
    return PROMPT.format(title=t["title"], body=t["body"], commands=COMMANDS)


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
    record_base(w)


def record_base(w: Path) -> dict:
    """The checkout's own suite before any agent touches it, recorded as policybench records it (#221, #308): `base_green`, `base_suite`,
    `tests_collected`, in `.bench-arm.json`. A red base is recorded, not hidden: `score` carries the fact into every row."""
    py = str(w / ".venv/bin/python")
    t = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"], cwd=w, capture_output=True, text=True, timeout=1800)
    n = subprocess.run([py, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=w, capture_output=True, text=True, timeout=600).stdout
    last = (n.strip().splitlines() or [""])[-1]
    m = re.search(r"(\d+) tests? collected", last)
    meta = {"base_green": t.returncode == 0, "base_suite": (t.stdout.strip().splitlines() or [""])[-1],
            "tests_collected": int(m.group(1)) if m else None}
    (w / ".bench-arm.json").write_text(json.dumps(meta) + "\n")
    return meta


def run_one(issue: str, arm: str, rep: int) -> str:
    tag = f"{issue}-{arm}-r{rep}"
    out = B / "runs" / tag
    if (out / "end").exists():
        return f"skip {tag}"
    out.mkdir(parents=True, exist_ok=True)
    w = B / "work" / tag
    checkout(w)
    t = json.loads(sh(["gh", "issue", "view", issue, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
    cmd = ["claude", "-p", story_prompt(t), "--model", MODEL, "--output-format",
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

_FETCH_SEG = re.compile(r"(^|\s)(grep|rg|egrep|sed\s+-n|head|tail|cat|nl|awk)\b")
_QUERY = re.compile(r"devkb\s+(symbol|uses|outline|pack|docs|misses|tests|config|flows|review)\b(.*)")
REFETCH_WINDOW = 2
_FILE_EXT = "py|h|hh|hpp|c|cc|cpp|cxx|ts|tsx|js|jsx|json|md|yml|yaml|toml|rs|go|java|sh|txt|cfg|ini"


def distinctive(t: str) -> bool:
    """A target an agent could only re-fetch on purpose: a file with an extension, a name with `_` (but not a dunder such as `__init__`) or inner capitals, or a long
    one. `cpp`, `resolve`, `constant` or `shadow` are words, and a grep that mentions one is not a second look at the answer."""
    return bool(re.search(rf"\.(?:{_FILE_EXT})$", t)) or ("_" in t and not (t.startswith("__") and t.endswith("__"))) or bool(re.search(r"[a-z][A-Z]", t)) or len(t) >= 9


def devkb_targets(name: str, inp: dict) -> list[str]:
    """What one devkb query asked about: the names and files it was given . A path counts by its
    base name, `Class::method` and `a.b` by the last part; a regex, a free-text docs query and a name under 3 chars
    carry no target."""
    raw: list[str] = []
    if name in ("mcp__devkb__search_docs", "mcp__devkb__docs"):
        return []                                                     # free text, as the shell form `devkb docs` is
    if name.startswith("mcp__devkb"):
        raw = [str(inp.get(k, "")) for k in ("query", "subject", "path", "name") if inp.get(k)]
    elif name == "Bash":
        c = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "", inp.get("command", "") or "", flags=re.S)
        for seg in re.split(r"&&|\|\||;|\||\n", c):
            m = _QUERY.search(seg)
            if not m or m.group(1) in ("docs", "misses"):
                continue
            rest = re.sub(r"--project(?:=|\s+)\S+", "", m.group(2))
            args = [a.strip("'\"") for a in rest.split() if not a.startswith("-")]
            if m.group(1) == "pack":
                args = args[1:]                                      # the pack's kind (file, refactor, change, error)
            raw += args[:1]
    out = []
    for r in raw:
        for part in r.split(","):
            part = part.strip()
            if not part or part.startswith("re:") or " " in part:
                continue
            if re.search(rf"\.(?:{_FILE_EXT})$", part):
                t = part.split("/")[-1]                                  # a file: its base name
            else:
                t = re.split(r"::|\.|/", part)[-1]                       # Class::method, a.b, a path without extension
            if distinctive(t) and t not in out:
                out.append(t)
    return out


def fetch_kind(name: str, inp: dict, targets: list[str]) -> str | None:
    """'grep' / 'read' when this call searches or reads text that names one of the targets; else None. A devkb command
    is never a re-fetch."""
    if name in ("Grep", "Glob"):
        text, kind = f"{inp.get('pattern', '')} {inp.get('path', '')}", "grep"
    elif name == "Read":
        text, kind = str(inp.get("file_path", "")), "read"
    elif name == "Bash":
        text, kind = "", None
        for seg in re.split(r"&&|\|\||;|\n", inp.get("command", "") or ""):
            if _QUERY.search(seg) or not _FETCH_SEG.search(seg):
                continue
            k = "grep" if re.search(r"(^|\s)(grep|rg|egrep)\b", seg) else "read"
            if any(re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", seg) for t in targets):
                return k
        return None
    else:
        return None
    return kind if any(re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", text) for t in targets) else None


def refetch(calls: list[tuple[str, dict]], window: int = REFETCH_WINDOW) -> dict:
    """How often an agent fetches again what devkb just answered. For each devkb navigation query with a target, did a
    grep, rg, Grep, Read, sed, cat or head naming that target follow, in the same shell command or within `window`
    calls? {queries: with a target, refetched, grep, read, outline_read}. The count is of queries, each at most once; targets are
    distinctive names and files only. An `outline` followed by a read of the file and no grep is `outline_read`, not `refetched`:
    reading the range the outline pointed at is its use. A re-fetch measures what devkb did not replace."""
    q = rf = g = r = ow = 0
    for i, (name, inp) in enumerate(calls):
        if not (name.startswith("mcp__devkb") or (name == "Bash" and _QUERY.search(inp.get("command", "") or ""))):
            continue
        targets = devkb_targets(name, inp)
        if not targets:
            continue
        outline = name == "mcp__devkb__outline" or (name == "Bash" and (_QUERY.search(inp.get("command", "") or "") or [None, None, ""])[1] == "outline")
        q += 1
        kinds = []
        if name == "Bash":                                   # a later segment of the same command
            segs = re.split(r"&&|\|\||;|\n", inp.get("command", "") or "")
            seen = False
            for seg in segs:
                if _QUERY.search(seg):
                    seen = True
                elif seen:
                    k = fetch_kind("Bash", {"command": seg}, targets)
                    kinds += [k] if k else []
        for nm, ip in calls[i + 1:i + 1 + window]:
            k = fetch_kind(nm, ip, targets)
            kinds += [k] if k else []
        if outline and kinds and "grep" not in kinds:
            ow += 1                                          # an outline, then a read of the file: what the outline is for
        elif kinds:
            rf += 1
            g += "grep" in kinds
            r += "read" in kinds
    return {"queries": q, "refetched": rf, "grep": g, "read": r, "outline_read": ow}



def redact(text: str, root: str | None = None) -> str:
    """Recorded hook text names the repository it served, which is a run's checkout under the owner's home directory: a row
    that is committed or shared must not carry it (#356). The checkout becomes `<checkout>`, the home directory `~`."""
    if root:
        text = text.replace(root, "<checkout>")
    return text.replace(str(Path.home()), "~")


def transcript(path: Path) -> dict:
    sys.path.insert(0, str(REPO / "bench" / "audit"))
    from toolmix import classify, devkb_queries, size  # noqa: PLC0415
    kinds, calls, chars, msgs = {}, Counter(), Counter(), set()
    res, session, dq, nav, own, outs, edited, root, seen_ctx, first_ctx = {}, None, 0, 0, 0, {}, False, None, 0, None
    backgrounded = 0
    seq: list[tuple[str, dict]] = []                       # every tool call in order, for refetch()
    hook_outputs = []                                      # what each hook run said (hook_response events, #330)
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            session, root = e.get("session_id"), e.get("cwd") or root
        if e.get("type") == "result":
            res = e
        if e.get("type") == "system" and e.get("subtype") == "hook_response" and (e.get("output") or "").strip():
            try:                                   # the reminder or answer is the hook's additionalContext
                text = json.loads(e["output"]).get("hookSpecificOutput", {}).get("additionalContext") or e["output"]
            except (ValueError, AttributeError):
                text = e["output"]
            hook_outputs.append(redact(str(text), root))
        m = e.get("message")
        if not isinstance(m, dict):
            continue
        if e.get("type") == "assistant" and m.get("id"):
            msgs.add(m["id"])
            outs[m["id"]] = max(outs.get(m["id"], 0), (m.get("usage") or {}).get("output_tokens", 0))
            u = m.get("usage") or {}
            seen_ctx = max(seen_ctx, sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
            if first_ctx is None:                  # the run's starting context: the policy, hook and tool text, before any work (#331)
                first_ctx = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        for x in m.get("content") or []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_result" and "was moved to the background" in (
                    x["content"] if isinstance(x.get("content"), str) else json.dumps(x.get("content"))):
                backgrounded += 1                     # a command the Bash tool backgrounded at its timeout (#334)
            if x.get("type") == "tool_use":
                k = "devkb" if x["name"].startswith("mcp__devkb") else classify(x["name"], x.get("input", {}))
                kinds[x["id"]] = k
                seq.append((x["name"], x.get("input") or {}))
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
    cut_off = not res                                     # no final result message: the run was cut off (#303)
    if cut_off:
        ctx = seen_ctx                                    # the largest context any model call had: a floor, not zero
    for mu in (res.get("modelUsage") or {}).values():    # cumulative per model, when present
        ctx = max(ctx, sum(mu.get(k, 0) for k in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")))
    out = sum(mu.get("outputTokens", 0) for mu in (res.get("modelUsage") or {}).values()) or sum(outs.values())
    fired, actions = guardrail_actions(session)
    # turns: the result's num_turns counts only the last turn of a session (#258); each assistant message is one
    # model call. out_tokens: modelUsage holds the session's totals; per-message usage in the stream is partial.
    return {"session": session, "turns": len(msgs), "cost": None if cut_off else res.get("total_cost_usd", 0), "cut_off": cut_off, "first_ctx": first_ctx, "backgrounded": backgrounded,
            "hook_outputs": len(hook_outputs), "hook_first_output": hook_outputs[0][:400] if hook_outputs else None,
            "model_calls": len(msgs), "ctx_tokens": ctx, "out_tokens": out,
            "devkb_queries": dq, "devkb_nav": nav, "devkb_selftest": own, "calls": dict(calls), "chars": dict(chars), "guardrail_fired": fired,
            "guardrail_actions": actions, "refetch": refetch(seq)}


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
        import policybench          # the shared scoring (#308); imported here because policybench imports this module
        suite = policybench.run_suite(w)                          # the full suite, the failed ids, and the flaky rule (#301)
        meta = json.loads((w / ".bench-arm.json").read_text()) if (w / ".bench-arm.json").exists() else {}
        acc = B / "accept" / f"{issue}.py"                       # story-specific acceptance, if written
        a = subprocess.run([str(w / ".venv/bin/python"), str(acc), str(w)], capture_output=True, text=True,
                           timeout=3600) if acc.exists() else None
        rows.append({"run": out.name, "issue": issue, "arm": arm, "rep": rep, "exit": end["exit"], "seconds": end["seconds"], **suite,
                     "accept_sha256": hashlib.sha256(acc.read_bytes()).hexdigest() if acc.exists() else "",          # which check scored it (#223)
                     "base_green": meta.get("base_green"), "base_suite": meta.get("base_suite"),                       # #221
                     "tests_collected": meta.get("tests_collected"),
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
