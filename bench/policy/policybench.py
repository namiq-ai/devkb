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
import tempfile
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
         "outline": "origin/main",                                # #218 D2: main's devkb, outline on first open
         "hookmain": "origin/main",                               # #375: the ticket's base, the hook of POLICY_HOOK_MAIN
         "teachall": "origin/main",                               # #375: the ticket's base, the hook of POLICY_TEACHALL
         # #366: main's devkb with the policy a user's repository holds, not this repository's own process text
         "userpolicy": "origin/main",                             # AGENTS.md/CLAUDE.md exactly as `devkb init` writes them
         "short": "origin/main",                                  # the same, the block cut to the lines agents act on
         "inject": "origin/main",                                 # userpolicy, plus the pack of the ticket's file in the prompt
         "rmain": "origin/main",                                  # workflow router: the router commit's devkb and guardrail, no router
         "router": "origin/main",                                 # the same, plus the prompt router (devkb hook prompt)
         "ctx": "origin/main",                                    # the same, plus the silent task-recording hook (devkb hook context)
         "userinit": "origin/main",                               # everything `devkb init` writes: + its MCP server, no guardrail
         "both": "origin/main"}                                   # main's policy and hook (the shell entry point) + the devkb MCP server (the tool entry point)
# Tri-mode arms take their devkb (CLI, graph build, hook) from a tool environment built from an exact commit, never
# from the checkout the agent edits (#225). POLICY_RELEASE / POLICY_MAIN override the refs.
ENV_REF = {"release": lambda: os.environ.get("POLICY_RELEASE") or toolenv.latest_release(),
           "main": lambda: os.environ.get("POLICY_MAIN") or "origin/main",
           "noteach": lambda: os.environ.get("POLICY_MAIN") or "origin/main",
           "outline": lambda: os.environ.get("POLICY_MAIN") or "origin/main",
           # a hook version against another on the same checkouts (#375): the checkout follows POLICY_MAIN (the ticket's
           # base), the devkb and hook come from a fixed commit each
           "hookmain": lambda: os.environ.get("POLICY_HOOK_MAIN") or "origin/main",
           "teachall": lambda: os.environ["POLICY_TEACHALL"],
           # rmain and router differ in one thing, the UserPromptSubmit hook: same devkb commit (POLICY_ROUTER), same checkout
           **{a: (lambda: os.environ["POLICY_ROUTER"]) for a in ("rmain", "router", "ctx")},
           **{a: (lambda: os.environ.get("POLICY_MAIN") or "origin/main") for a in ("userpolicy", "short", "inject", "userinit", "both")}}
# Every devkb arm keeps the answers its agents were given (#218); D1 and D2 are the two direct-path candidates.
ARM_ENV = {"release": {"DEVKB_GUARDRAIL_KEEP": "1"}, "main": {"DEVKB_GUARDRAIL_KEEP": "1"},
           "noteach": {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_TEACH": "0"},   # main without D1 (on by default, #267)
           "outline": {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_OUTLINE": "1"},
           "hookmain": {"DEVKB_GUARDRAIL_KEEP": "1"},
           "teachall": {"DEVKB_GUARDRAIL_KEEP": "1", "DEVKB_GUARDRAIL_TEACH_ALL": "1"},   # the setting, off by default (#375)
           **{a: {"DEVKB_GUARDRAIL_KEEP": "1"} for a in ("userpolicy", "short", "inject", "userinit", "rmain", "router", "ctx", "both")}}
# #366: the policy text of the user-facing arms. "full" is the block `devkb init` writes (devkb.init.AGENTS_BLOCK of the
# arm's devkb), "short" the candidate below; the checkout's CLAUDE.md is then `@AGENTS.md`, as init writes it.
USER_POLICY = {"userpolicy": "full", "short": "short", "inject": "full", "userinit": "full"}
USER_INIT = "lean-pack"                    # the toolset `devkb init` registers by default (devkb/init.py, --toolset)
SHORT_BLOCK = """## devkb: ask the graph before you search or read code

`.devkb/` holds a graph of this repository's code; every answer cites the line that proves it.
- `devkb symbol NAME --source`: where NAME is defined, and its body (instead of `grep -n "def NAME" -A30`)
- `devkb uses NAME`: every use of NAME, grouped by the function it is in (instead of `grep -rn NAME`)
- `devkb pack --project . file PATH`: before you edit PATH: who calls into it, and the tests to run
- `devkb pack --project . refactor NAME`: before you change a function: its callers at any depth, and their tests
A pack marked **Complete** is the whole answer. To learn how code is written, read the file: the graph does not store it."""
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
{commands}
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


# The same arms with the ticket's location withheld (#337): "Where to start" removed, the files in "Scope" and every file or
# name it gave masked wherever the ticket repeats them. Set up exactly as their base arm (same template); only the text differs.
HIDE_LOCATION = {"nonehid": "none", "mainhid": "main", "rmainhid": "rmain", "routerhid": "router", "ctxhid": "ctx", "bothhid": "both"}
WITHHELD = "(withheld)"
_SECTION = re.compile(r"(?ms)^(?:\*\*(?P<h>[^*\n]+?):?\*\*:?|#{1,6}[ \t]+(?P<g>[^\n]+?)[ \t]*$)(?P<t>.*?)"
                      r"(?=^\*\*[^*\n]+?:?\*\*|^#{1,6}[ \t]|\Z)")
_FENCED = re.compile(r"(?ms)^(```|~~~).*?^\1[ \t]*$")
_FILE = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)*[\w.-]+\.(?:py|md|json|jsonl|toml|ya?ml|sh|c|cc|cpp|h|hpp|cs|ts|js)\b")
_NAME = re.compile(r"[A-Za-z_][\w.]*(?:::[A-Za-z_]\w*)*")
_VERSION = re.compile(r"^v?\d")


def _sections(body: str):
    """(heading, start, end) of each `**Heading:**` or `## Heading` section, outside code fences; an inline
    `**Where to start:**` (not at a line start) is its own section up to the next blank line."""
    plain = _FENCED.sub(lambda m: " " * len(m.group(0)), body)     # a bold line inside a fence is not a section
    out = [((m.group("h") or m.group("g") or "").strip().lower(), m.start(), m.end()) for m in _SECTION.finditer(plain)]
    if not any(h.startswith("where to start") for h, _a, _b in out):
        m = re.search(r"\*\*Where to start:?\*\*:?.*?(?=\n\s*\n|\Z)", plain, re.S)
        if m:
            out.append(("where to start", m.start(), m.end()))
    return out


def _code_like(n: str, body: str = "") -> bool:
    if _VERSION.match(n) or any(len(part) < 2 for part in re.split(r"\.|::", n)):
        return False                              # v0.2.11, e.g: not code names (#385 review)
    if re.search(r"(?:Error|Exception|Warning)$", n):
        return False                              # an exception is the symptom, not the place (#385 review, round 2)
    if n.isupper() and body and re.search(rf"(?:\$|\b){re.escape(n)}=|\${re.escape(n)}\b", body):
        return False                              # an environment variable set or read in the ticket: the reproduction
    return "_" in n or "." in n or "::" in n or bool(re.search(r"[a-z][A-Z]", n))


def location_names(body: str) -> list[str]:
    """What the location gives away, longest first: the files and code names a ticket's "Where to start" names (with the
    stems of its dotted names and of its files), and the files its "Scope" names. A code name looks like code (an
    underscore, a dot, `::` or CamelCase), so plain words and command names (`run`, `uses`, `devkb`) stay."""
    names: set[str] = set()

    def add_file(f: str) -> None:
        base = f.rsplit("/", 1)[-1]
        names.update({f, base})
        stem = base.rsplit(".", 1)[0]
        # the module's own name, where the ticket uses it as code (`storybench.ALLOW`, `import read_tools`), never a word
        # like "service" in prose (#385 review)
        if "_" in stem or re.search(rf"\b{re.escape(stem)}\.(?:[a-z_]\w*\(|[A-Z][A-Z_]+\b)|\b(?:import|from)\s+{re.escape(stem)}\b"
                                    rf"|`{re.escape(stem)}`", body):           # or named alone as code: `policybench`
            names.add(stem)
    for h, a, b in _sections(body):
        t = body[a:b]
        if h.startswith("scope"):                 # a Scope file or code name is withheld wherever it appears (#385 review)
            for f in _FILE.findall(t):
                add_file(f)
            for code in re.findall(r"`([^`\n]+)`", _FILE.sub(" ", t)):
                for n in _NAME.findall(code):
                    n = n.rstrip(".")
                    if len(n) > 2 and (_code_like(n, body) or (n[:1].isupper() and len(n) >= 5)):
                        names.add(n)          # `ReadTools.resolve`, `_by_module_name`, `Staleness`
        if h.startswith("where to start"):
            for f in _FILE.findall(t):
                add_file(f)
            for n in _NAME.findall(_FILE.sub(" ", t)):
                n = n.rstrip(".")
                if len(n) > 2 and _code_like(n, body):
                    names.add(n)
                    parts = re.split(r"\.|::", n)
                    names.update(p for p in parts if len(p) > 2 and _code_like(p, body))      # `_match` of `x._match`
                    if len(parts) > 1 and (_code_like(parts[0], body) or (parts[0][:1].isupper() and len(parts[0]) >= 5)):
                        names.add(parts[0])                                           # the module or class: `build_symbols`, `Packer`
    return sorted(names, key=len, reverse=True)


def in_own_code(w: Path | None, name: str) -> bool:
    """Whether a code name occurs in the checkout's own code (not its corpus, tests or docs). A name that does not, such
    as a corpus function in the symptom (#114's `count_digits`), says nothing about where to fix (#385 review, round 3).
    Without a checkout, every name counts."""
    if w is None or not (Path(w) / ".git").exists():
        return True
    for part in [name] + [p for p in re.split(r"\.|::", name) if len(p) > 2]:   # `ReadTools.resolve` is written apart
        rc = subprocess.run(["git", "-C", str(w), "grep", "-qwF", part, "--", ".", ":!corpus", ":!tests", ":!docs"],
                            capture_output=True).returncode
        if rc != 1:                               # found (0), or git failed: withhold rather than leak (#385 review, round 4)
            return True
    return False


def without_location(title: str, body: str, w: Path | None = None) -> tuple[str, str]:
    """(title, body) with the location withheld (#337): the "Where to start" section is replaced by one line; every name
    `location_names` gives is masked wherever title and body repeat it, with what qualifies it (`Packer._resolve`,
    `bench/policy/x.py`), and so are the line numbers around it (`x.py:1471`, `L636`). Code fences are masked too: a
    reproduction that names the place gives the place away."""
    names = [n for n in location_names(body) if _FILE.fullmatch(n) or in_own_code(w, n)]
    pieces, last = [], 0
    for h, a, b in sorted(_sections(body), key=lambda x: x[1]):
        if a < last:
            continue
        pieces.append(body[last:a])
        pieces.append("**Where to start:** (withheld for this benchmark run)\n\n" if h.startswith("where to start") else body[a:b])
        last = b
    pieces.append(body[last:])
    body = "".join(pieces)

    def mask(text: str) -> str:
        for n in names:
            text = re.sub(rf"(?:(?<=[^\w])|^)(?:[\w.-]*(?:\.|::|/))*{re.escape(n)}(?![\w-])", WITHHELD, text, flags=re.M)
        # a withheld name's line number goes with it (`x.py:1471`, `name (L636)`); other line numbers, such as a corpus
        # file's in a Done-when, are the ticket's evidence and stay (#385 review, round 2)
        text = re.sub(rf"{re.escape(WITHHELD)}(?::\d+(?:-\d+)?)+", WITHHELD, text)
        text = re.sub(rf"({re.escape(WITHHELD)}`?)(\s*[(,]\s*)~?L\d+(?:[-\u2013]L?\d+)?\)?", r"\1", text)
        return text
    return mask(title), mask(body)


def arms_for(arms: list[str]) -> list[str]:
    """The arms a batch runs and scores: with POLICY_HIDE_START=1 (the ticket's option name), every arm runs in its hidden
    form (#337), and an arm that has none stops the batch rather than keep the location unnoticed (#385 review). `run`
    and `score` both go through here."""
    if os.environ.get("POLICY_HIDE_START") != "1":
        return arms
    hid = {v: k for k, v in HIDE_LOCATION.items()}
    missing = [a for a in arms if a not in hid and a not in HIDE_LOCATION]
    if missing:
        raise SystemExit(f"POLICY_HIDE_START=1: no hidden form for arm(s) {', '.join(missing)}; hidden forms exist for "
                         f"{', '.join(sorted(hid))}")
    return [hid.get(a, a) for a in arms]


def split_arm(arm: str) -> tuple[str, bool]:
    """(the arm a run is set up as, whether its ticket's location is withheld) (#337)."""
    return HIDE_LOCATION.get(arm, arm), arm in HIDE_LOCATION


def ticket_for(issue: str) -> dict:
    """The ticket as filed (title, body), with the tickets done in the same job (bench/policy/groups.json)."""
    t = json.loads(sb.sh(["gh", "issue", "view", issue, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
    for extra in GROUPS.get(issue, []):
        t2 = json.loads(sb.sh(["gh", "issue", "view", extra, "-R", "namiq-ai/devkb", "--json", "title,body"]).stdout)
        t = {"title": t["title"] + f" (with #{extra})", "body": t["body"] + f"\n\n# Same work: #{extra}, " + t2["title"] + "\n\n" + t2["body"]}
    return t


def run_prompt(issue: str, run_arm: str, w: Path) -> str:
    """The prompt a run of `run_arm` is given: the ticket as filed, or with its location withheld for a hidden arm (#337)."""
    t = ticket_for(issue)
    return prompt_for(issue, t["title"], t["body"], w, split_arm(run_arm)[1])


def prompt_for(issue: str, title: str, body: str, w: Path, hide: bool = False) -> str:
    """The prompt an agent is given for a ticket: as filed, or with its location withheld (#337)."""
    if hide:
        title, body = without_location(title, body, w)
    return (sb.PROMPT if issue == "117" else PROMPT).format(title=title, body=without_missing_data(body, w),
                                                           commands=sb.COMMANDS)


def base_for(arm: str, issue: str | None = None) -> str:
    """The commit an arm's checkout is made from. The arms that follow the batch's main (POLICY_MAIN) can follow a ticket's own base
    instead: POLICY_BASES="118=SHA,120=SHA". One batch can then hold several tickets, shuffled together, each at its own base."""
    base, main = BASES[arm], os.environ.get("POLICY_MAIN")
    per = dict(x.split("=", 1) for x in os.environ.get("POLICY_BASES", "").split(",") if "=" in x)
    return per.get(str(issue), base) if issue is not None and main and base == main else base


def checkout(w: Path, arm: str, issue: str | None = None):
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(sb.REPO), "archive", base_for(arm, issue)], check=True, capture_output=True).stdout
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
    arm_files(w, arm, env)
    if arm != "nonekeep" and (arm == "none" or os.environ.get("POLICY_EQUAL_SUITE", "1") == "1"):
        trim_tests(w)                                 # every arm runs the same suite as `none` (#331); nonekeep keeps all
    if env and arm != "userinit":                     # the arm's hook runs the tool environment's guardrail; `devkb init`
                                                      # installs none, so userinit has no hook (#366 review)
        st_path = w / ".claude" / "settings.json"
        st = json.loads(st_path.read_text()) if st_path.exists() else {}
        st["hooks"] = toolenv.hooks_settings(env, router=(arm == "router"), context=(arm == "ctx"))
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
                                capture_output=True, text=True, timeout=1800, env=suite_env())
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
        txt = t.read_text(errors="replace")
        if "devkb_guardrail" in txt or "hook_replay" in txt:     # hook_replay runs the guardrail script as a subprocess (#401)
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


def permissions(arm: str) -> tuple[list[str], list[str]]:
    """(--allowedTools, --disallowedTools) of a run: the same rules in every arm (#369); an arm without devkb also
    denies devkb in both forms (#335)."""
    base = split_arm(arm)[0]                          # a hidden arm (#337) is denied what its base arm is
    return list(sb.ALLOW), sb.DENY + (["Bash(devkb:*)", "Bash(.venv/bin/devkb:*)"] if base in ("none", "nonekeep") else [])


# The ways an agent can reach devkb, per arm: `shell` (a `devkb ...` command run through Bash, which the policy text teaches), `hook` (the guardrail
# that answers or reminds before a grep, so the agent does not have to ask) and `tool` (an MCP tool in the model's own tool list, which it picks
# like `Grep`). An arm not listed is not checked. A run records what it really had (`entry_points`) and what differs from this (#entry-points).
ENTRY_POINTS = {"none": (False, False, False), "nonekeep": (False, False, False),
                "main": (True, True, False), "both": (True, True, True), "userinit": (True, False, True)}


def init_tools(stream: Path) -> list[str]:
    """The tool names the model was given, from the stream's first `init` event; empty when there is none."""
    try:
        for line in stream.read_text().splitlines():
            if line.startswith("{") and '"subtype":"init"' in line.replace(" ", ""):
                return list(json.loads(line).get("tools") or [])
    except (OSError, ValueError):
        pass
    return []


def entry_points_observed(arm: str, w: Path, env: dict, stream: Path) -> dict:
    """What a run really had: `tool` = an `mcp__devkb*` tool in the model's tool list; `shell` = `devkb` runnable by the agent (on its PATH and not denied);
    `hook` = the checkout wires the guardrail into PreToolUse and the run did not switch it off; `policy` = the checkout's AGENTS.md has the devkb block."""
    tools = init_tools(stream)
    try:
        settings = json.loads((w / ".claude" / "settings.json").read_text())
        wired = any("devkb_guardrail" in h.get("command", "") for g in settings.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", []))
    except (OSError, ValueError):
        wired = False
    denied = any("devkb" in d for d in permissions(arm)[1])
    on_path = shutil.which("devkb", path=env.get("PATH")) is not None
    try:
        policy = "devkb:begin" in (w / "AGENTS.md").read_text()
    except OSError:
        policy = False
    return {"tools_listed": len(tools), "tool": any(t.startswith("mcp__devkb") for t in tools), "shell": on_path and not denied,
            "hook": wired and env.get("DEVKB_GUARDRAIL", "1") != "0", "policy": policy}


def entry_point_problems(arm: str, observed: dict) -> list[str]:
    """What differs from the arm's design (ENTRY_POINTS), as lines to print; none for an arm that is not listed."""
    want = ENTRY_POINTS.get(split_arm(arm)[0])
    if want is None:
        return []
    names = ("shell", "hook", "tool")
    problems = [f"{n}: expected {'present' if w_ else 'absent'}, the run had it {'present' if observed.get(n) else 'absent'}"
                for n, w_ in zip(names, want) if bool(observed.get(n)) != w_]
    if observed.get("tools_listed", 0) == 0:
        problems.append("the stream has no init event, so the tool list could not be read")
    return problems


def claude_cmd(issue: str, arm: str, prompt: str, mcp: str) -> list[str]:
    """The `claude` command of a run. Only `arm` decides the deny list's devkb entries (permissions); everything else is
    the same in every arm (#369)."""
    if sb.COMMANDS.strip() not in prompt:            # every arm's prompt says how to run commands, whatever came before
        raise ValueError(f"the {arm} prompt lacks the command rules (storybench.COMMANDS, #369)")
    allow, deny = permissions(arm)
    return ["claude", "-p", prompt, "--model", sb.MODEL, *SOURCES, "--output-format",
            "stream-json", "--verbose", "--max-turns", "250" if issue in ("117", "131") else "150", "--permission-mode",
            "acceptEdits", "--strict-mcp-config", "--mcp-config", mcp, "--allowedTools", *allow, "--disallowedTools", *deny,
            "--include-hook-events"]                  # the stream then records what the hook said to the agent (#330)


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
                                                         ":(exclude)bench/policy/no-mcp.json", ":(exclude)bench/policy/runs-archive")      # archiving a run is not a stray write


TEMPLATES = Path(os.environ.get("POLICY_TEMPLATES_DIR") or CACHE / "policy-templates")   # outside the repository too (#340)


def user_policy(env: dict, kind: str) -> tuple[str, str]:
    """(AGENTS.md, CLAUDE.md) as `devkb init` of the arm's devkb writes them into a repository with neither file (#366);
    with `kind` "short", the block is SHORT_BLOCK instead of devkb's AGENTS_BLOCK."""
    code = ("import sys\nfrom devkb.init import AGENTS_BLOCK, _set_block\n"
            "block = AGENTS_BLOCK if sys.argv[1] == 'full' else sys.argv[2]\n"
            "print(_set_block('', block), end='\\0')\nprint(_set_block('', '@AGENTS.md'), end='')\n")
    p = subprocess.run([sys.executable, "-P", "-c", code, kind, SHORT_BLOCK], capture_output=True, text=True, check=True,
                       env=dict(os.environ, PYTHONPATH=env["src"]))
    agents, claude = p.stdout.split("\0")
    return agents, claude


INJECT = ("Before this session, devkb ran `devkb pack --project . file {path}` for the file the ticket points to. Its "
          "answer:\n\n{pack}\n\n---\n\n")


def start_files(body: str, w: Path) -> list[str]:
    """The checkout's files the ticket's "Where to start" points to, in the ticket's order (#366 review): a path, a file
    name, or the module of a dotted name (`cli.main` -> the one `cli.py`), resolved to the single file of that name
    outside tests/ and corpus/; Scope's files, in order, when "Where to start" names none."""
    def resolve(name: str) -> str | None:
        if "/" in name:
            return name if (w / name).is_file() else None
        hits = [str(p.relative_to(w)) for p in w.rglob(name) if p.is_file()
                and not str(p.relative_to(w)).startswith(("tests/", "corpus/", "bench/results/", "."))]
        return hits[0] if len(hits) == 1 else None

    def files_in(section: str) -> list[str]:
        found = [(m.start(), m.group(0)) for m in _FILE.finditer(section)]
        found += [(m.start(), m.group(1).split(".")[0] + ".py")
                  for m in re.finditer(r"`([A-Za-z_]\w*\.[A-Za-z_][\w.]*)\(?\)?`", section) if not _FILE.fullmatch(m.group(1))]
        names = [n for _pos, n in sorted(found)]                    # in the order the ticket gives them
        out = []
        for n in names:
            r = resolve(n)
            if r and r not in out:
                out.append(r)
        return [f for f in out if not (f.startswith("tests/") or "/test_" in f)] or out      # the code, before its tests

    secs = {h: body[a:b] for h, a, b in _sections(body)}
    start = next((t for h, t in secs.items() if h.startswith("where to start")), "")
    scope = next((t for h, t in secs.items() if h.startswith("scope")), "")
    return files_in(start) or files_in(scope)


def injected_context(issue: str, w: Path, devkb_bin: str) -> str:
    """The `inject` arm's first-turn context (#366): the file pack of the first file `start_files` gives, computed with the arm's devkb on the run's own graph; nothing when it names no file."""
    files = start_files(ticket_for(issue)["body"], w)
    if not files:
        return ""
    p = subprocess.run([devkb_bin, "pack", "--project", str(w), "file", files[0]], cwd=w, capture_output=True, text=True,
                       timeout=300)
    pack = p.stdout.strip().replace(str(w), ".")
    return INJECT.format(path=files[0], pack=pack) if p.returncode == 0 and pack else ""


def arm_files(w: Path, arm: str, env: dict | None) -> None:
    """The policy files an arm's checkout holds (#366): a user-facing arm gets what `devkb init` writes, nothing of
    this repository's own process text; the other arms keep the checkout's files."""
    if arm in USER_POLICY:
        write_user_policy(w, env, USER_POLICY[arm])
    if arm in ("userinit", "both"):                  # and the rest of what a default `devkb init` writes: the MCP server
        py = Path(env["bin"]).parent / "python"           # the server needs devkb's `mcp` extra, as a user installs it
        if subprocess.run([str(py), "-c", "import mcp"], capture_output=True).returncode:
            sb.sh(["uv", "pip", "install", "-q", "--python", str(py), "mcp>=1.23,<2"])
        (w / ".mcp.json").write_text(user_mcp(env))
    if arm == "userinit":
        (w / ".claude" / "settings.json").unlink(missing_ok=True)   # init writes none without --claude-hook; `both` keeps the checkout's hooks


def user_mcp(env: dict) -> str:
    """The `.mcp.json` a default `devkb init` of the arm's devkb writes into a repository without one (#366 review)."""
    code = "import sys\nfrom pathlib import Path\nfrom devkb.init import _mcp\nprint(_mcp(Path(sys.argv[1]), sys.argv[2]), end='')\n"
    with tempfile.TemporaryDirectory() as d:
        return subprocess.run([sys.executable, "-P", "-c", code, d, USER_INIT], capture_output=True, text=True, check=True,
                              env=dict(os.environ, PYTHONPATH=env["src"])).stdout


def write_user_policy(w: Path, env: dict | None, kind: str) -> None:
    if not env:
        raise RuntimeError("a user-policy arm needs a tool environment (ENV_REF)")
    agents, claude = user_policy(env, kind)
    (w / "AGENTS.md").write_text(agents)
    (w / "CLAUDE.md").write_text(claude)


def template_for(arm: str, issue: str | None = None) -> Path:
    """One prepared checkout per arm and base commit (files, corpus, venv, graphs, base suite checked), made once and
    copied for each run: the 4-5 minutes of setup a run used to repeat (POLICY_TEMPLATES=0 turns it off)."""
    base = sb.sh(["git", "-C", str(sb.REPO), "rev-parse", f"{base_for(arm, issue)}^{{commit}}"]).stdout.strip()
    envc = toolenv.resolve(ENV_REF[arm]()) if arm in ENV_REF else "none"
    suite = "eq" if os.environ.get("POLICY_EQUAL_SUITE", "1") == "1" else "full"      # the suite is content: part of the key (#331)
    post = "-post" if os.environ.get("POLICY_PREREGISTER_POST") == "1" else ""      # it adds a hook to the checkout (#307)
    t = TEMPLATES / f"{arm}-{base[:12]}-{envc[:12]}-suite{suite}{post}"
    with toolenv.held(TEMPLATES / f".{t.name}.lock"):   # runs of one arm, in this or another benchmark process, wait
                                                        # for the same template: never built twice, never deleted in use
        if not (t / ".bench-ready").exists():
            if t.exists():
                shutil.rmtree(t)
            checkout(t, arm, issue)               # raises on a red base: then every run of this arm is refused
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


def setup_error(out: Path) -> str | None:
    """The line that says why a run died before it reached the model: no stream at all and a stderr that names an error (#379), e.g.
    `Error: Invalid MCP configuration`. Such a run is never scored; it is run again."""
    stream, err = out / "stream.jsonl", out / "stderr.log"
    if (stream.exists() and stream.stat().st_size > 0) or not err.exists():
        return None
    for line in err.read_text(errors="replace").splitlines():
        if line.strip().startswith("Error:"):
            return line.strip()[:200]
    return None


def finished(issue: str, arm: str, rep: int) -> bool:
    """The run has ended and is kept: not an error and not a refused red base, which are set up again (#305), and not a run that died of a
    setup error before the model (#379)."""
    run_dir = B / "runs" / f"p{issue}-{arm}-r{rep}"
    end = run_dir / "end"
    return end.exists() and json.loads(end.read_text()).get("exit") not in ("error", "base-red") and setup_error(run_dir) is None


def check_collisions(jobs: list[tuple[str, str, int]], resume: bool) -> list[str]:
    """A batch compares arms that ran together. A run whose directory already holds a finished run would be skipped, and the batch
    would then mix runs from two times and, often, two devkb commits. Refuse, naming them, unless `--resume` says to keep them;
    then list them. Returns the kept runs."""
    done = [f"p{i}-{arm}-r{r}" for i, arm, r in jobs if finished(i, arm, r)]
    if done and not resume:
        raise SystemExit(f"{len(done)} of these {len(jobs)} runs already exist and would be silently skipped: {', '.join(done[:6])}"
                         f"{' ...' if len(done) > 6 else ''}\nA batch compares arms that ran together: archive them (bench/policy/runs-archive/), "
                         "or move them aside, or pass --resume to keep them and run the rest (they are listed, not hidden).")
    if done:
        print(f"--resume: keeping {len(done)} finished runs: {', '.join(done)}", flush=True)
    return done


def _run_one(issue: str, arm: str, rep: int) -> str:
    tag = f"p{issue}-{arm}-r{rep}"
    if finished(issue, arm, rep):
        return f"skip {tag}"                          # only reached with --resume (the batch refuses otherwise)
    arm = split_arm(arm)[0]                           # #337: set up as the base arm; only the ticket's text differs (run_prompt)
    out = B / "runs" / tag
    out.mkdir(parents=True, exist_ok=True)
    w = work_dir() / tag
    try:
        if os.environ.get("POLICY_TEMPLATES", "1") == "1":
            from_template(template_for(arm, issue), w)
        else:
            checkout(w, arm, issue)
    except RuntimeError as e:                         # a red base (#221): recorded, not run or scored; set up again next batch (#305)
        (out / "end").write_text(json.dumps({"exit": "base-red", "seconds": 0, "error": str(e)[-400:]}))
        return f"refused {tag}: {e}"
    except Exception as e:  # noqa: BLE001  a setup that fails is recorded, never a run that silently disappears
        (out / "end").write_text(json.dumps({"exit": "error", "seconds": 0, "error": f"setup: {type(e).__name__}: {e}"[-400:]}))
        return f"error {tag}: setup failed: {e}"       # not a red base: run again in the next batch (#305)
    if arm in ("userinit", "both"):                  # init's own MCP server, as committed: its `devkb` is the arm's,
        mcp = str(w / ".mcp.json")                   # first on PATH (below), so the checkout stays clean (#366 review)
    elif arm.startswith("after"):                    # "cli": no MCP server, devkb only through the shell
        mcp = str(w / ".mcp.json")
        cfg = json.loads(Path(mcp).read_text())
        cfg["mcpServers"]["devkb"]["command"] = TOOL.get(arm, sb.DEVKB)
        Path(mcp).write_text(json.dumps(cfg, indent=2) + "\n")
    else:
        # one file per run, in its own directory, written whole and moved into place: a shared file rewritten while other runs' `claude` processes read it
        # through `--mcp-config` was read half-written ("MCP config is not a valid JSON") (#379)
        mcp = str(out / "no-mcp.json")
        tmp = out / f".no-mcp.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"mcpServers": {}}))
        os.replace(tmp, mcp)
    prompt = run_prompt(issue, tag.split("-")[1], w)
    if arm == "inject":                              # #366: the answer up front instead of advice
        prompt = injected_context(issue, w, tool_of(arm, toolenv.build(ENV_REF[arm]()))) + prompt
    if os.environ.get("POLICY_PREREGISTER_POST") == "1":
        prompt += SETTINGS_NOTE
    meta = json.loads((w / ".bench-arm.json").read_text())
    env_bin = tool_of(arm, toolenv.build(ENV_REF[arm]()) if arm in ENV_REF else None)
    cmd = claude_cmd(issue, arm, prompt, mcp)
    # The Bash tool backgrounds a command after 120 s by default; a full suite that runs about that long then costs the agent
    # extra turns to wait for it, in one arm and not the other (#334). Every arm gets the same, longer limit.
    limit = os.environ.get("POLICY_BASH_TIMEOUT_MS", "600000")
    env = dict(os.environ, BASH_DEFAULT_TIMEOUT_MS=limit, BASH_MAX_TIMEOUT_MS=limit,
               DEVKB_GUARDRAIL={"before": "0", "none": "0", "nonekeep": "0", "cli130": "enforce"}.get(arm, "1"),
               PATH=f"{Path(env_bin).parent}:{w / '.venv' / 'bin'}:{os.environ['PATH']}", **ARM_ENV.get(arm, {}))
    meta["prompt_sha256"] = hashlib.sha256(cmd[2].encode()).hexdigest()       # what the agent was told, checkable later
    meta["commands_sha256"] = hashlib.sha256(sb.COMMANDS.encode()).hexdigest()
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
    ep = entry_points_observed(arm, w, env, out / "stream.jsonl")
    ep_problems = entry_point_problems(arm, ep)
    (out / "end").write_text(json.dumps({"exit": code, "seconds": round(time.time() - t0), "entry_points": ep, "entry_point_problems": ep_problems,
                                         **({"contaminated": touched} if touched else {})}))
    try:                                              # scored now, while other agents run, not in a tail after the batch
        r = score_run(issue, out)
        if r:
            (out / "score.json").write_text(json.dumps(r) + "\n")
    except Exception as e:  # noqa: BLE001  `score` scores it later
        (out / "score-error.txt").write_text(str(e)[-2000:])
    return (f"done {tag} exit={code} {round(time.time() - t0)}s" + (f" CONTAMINATED the harness repository: {touched}" if touched else "")
            + (f" ENTRY POINTS DIFFER FROM THE ARM: {ep_problems}" if ep_problems else ""))


def _failed_ids(stdout: str) -> list[str]:
    """Test ids pytest -rfE reports as FAILED or ERROR (the summary lines), in order, without their messages."""
    ids = []
    for line in stdout.splitlines():
        if line.startswith(("FAILED ", "ERROR ")):
            tid = line.split(" ", 1)[1].split(" - ", 1)[0].strip()
            if tid and tid not in ids:
                ids.append(tid)
    return ids


def router_log(w: Path) -> list[dict]:
    """The prompt router's decisions in a run's checkout (`.devkb/router.jsonl`): route and size of what it pushed."""
    p = w / ".devkb" / "router.jsonl"
    try:
        return [{k: r.get(k) for k in ("route", "chars", "subjects")} for r in map(json.loads, p.read_text().splitlines())]
    except (OSError, ValueError):
        return []


def suite_env() -> dict:
    """The environment a checkout's own suite runs in: the benchmark's settings (`POLICY_ARMS`, `POLICY_MAIN`, ...) are left out. The suite has tests of the
    harness itself, and they read those variables (`score` filters its rows by `POLICY_ARMS`), so a batch of one arm made the base of that arm red."""
    return {k: v for k, v in os.environ.items() if not k.startswith("POLICY_")}


def run_suite(w: Path, timeout: int = 1800) -> dict:
    """The checkout's full suite, with the ids of what failed. A red suite is run in full once more (#301): a failed
    test is flaky (load-sensitive, recorded, not held against the change) only when the whole suite passes the second
    time. A test that passes alone but fails again in the second full run is order-dependent, which is the change's
    failure, so the suite stays red. (#260 re-ran the failed tests alone, which let an order dependence pass as flaky.)"""
    py = str(w / ".venv/bin/python")
    cmd = [py, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"]
    t = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=timeout, env=suite_env())
    last = (t.stdout.strip().splitlines() or [""])[-1]
    failed = _failed_ids(t.stdout)
    row = {"suite_pass": t.returncode == 0, "suite": last, "suite_failed": failed, "suite_flaky": []}
    if t.returncode == 0 or not failed:                 # green, or red with nothing to re-run (a crash): as it is
        return row
    r = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=timeout, env=suite_env())
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
            "router": router_log(w),                                                               # what the prompt router did
            "contaminated": end.get("contaminated") or [],                                         # #340
            "entry_points": end.get("entry_points"), "entry_point_problems": end.get("entry_point_problems") or [],   # which of shell, hook, tool the run had
            "devkb_commit": arm_meta.get("devkb_commit"), "hook_sha": arm_meta.get("hook_sha"),   # #225
            "telemetry": sum(len((d / ".devkb" / "process-api-telemetry.jsonl").read_text().splitlines())
                             for d in [w, *(w / "corpus" / r for r in sb.CORPUS_REPOS)]
                             if (d / ".devkb" / "process-api-telemetry.jsonl").exists()),
            **sb.transcript(out / "stream.jsonl")}


def score(issues):
    """Every run's row: the one saved when the run ended, unless its hidden check changed since (or POLICY_RESCORE=1)."""
    rows = []
    for issue in issues:
        only = set(arms_for(list(filter(None, os.environ.get("POLICY_ARMS", "").split(",")))))   # as `run` ran them
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
            why = setup_error(out)
            if why:
                print(out.name, f"SETUP ERROR (not scored; run again): {why}", flush=True)
                continue
            saved = json.loads((out / "score.json").read_text()) if (out / "score.json").exists() else None
            r = saved if saved and saved.get("accept_sha256") == sha and os.environ.get("POLICY_RESCORE") != "1" else score_run(issue, out)
            if not r:
                continue
            rows.append(r)
            print(r["run"], "pass" if r["acceptance"].get("pass") else "FAIL", "suite" if r["suite_pass"] else "SUITE-RED",
                  f"${r['cost']:.2f}" if r.get("cost") is not None else "cost ?", "devkb", r["devkb_queries"], "guard", r["guardrail_fired"], "log", r["dogfood_log"], flush=True)
    only = set(arms_for(list(filter(None, os.environ.get("POLICY_ARMS", "").split(",")))))
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


def check_arms(arms: list[str]) -> None:
    """Stop a batch before any run when an arm cannot say which commit its hook comes from (#375)."""
    if {"rmain", "router", "ctx", "rmainhid", "routerhid", "ctxhid"} & set(arms) and not os.environ.get("POLICY_ROUTER"):
        raise SystemExit("the rmain, router and ctx arms (and their hidden forms) need POLICY_ROUTER: the commit of the devkb they run (docs/specs/workflow-router.md)")
    if "teachall" in arms and not os.environ.get("POLICY_TEACHALL"):
        raise SystemExit("the teachall arm needs POLICY_TEACHALL: the commit whose hook it runs (#375)")


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
        os.environ.setdefault("POLICY_HOOK_MAIN", pinned)  # hookmain's hook is main as the batch starts, not a moving ref
        check_arms(arms)
        for k, v in BASES.items():
            if v == "origin/main":
                BASES[k] = os.environ["POLICY_MAIN"]
        print(f"batch pinned to main {os.environ['POLICY_MAIN'][:12]}", flush=True)
        arms = arms_for(arms)
        jobs = [(i, arm, r) for i in issues for arm in arms for r in range(first, first + reps)]
        check_collisions(jobs, "--resume" in a)
        random.Random(126).shuffle(jobs)
        with cf.ThreadPoolExecutor(par) as ex:
            for f in cf.as_completed([ex.submit(run_one, *j) for j in jobs]):
                print(f.result(), flush=True)
    else:
        score(issues)
