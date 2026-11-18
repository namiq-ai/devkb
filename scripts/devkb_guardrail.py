#!/usr/bin/env python3
"""devkb guardrail: a PreToolUse hook that reminds the agent to ask devkb before searching code by text.

Fires on the Grep tool, and on a Bash command that runs grep / rg / git grep as a search (not as a filter after a
pipe), when the search touches a repository devkb serves: a directory holding `.devkb/`, the devkb source tree
(`devkb/cli.py`), or the C/C++ corpus under ~/.cache/devkb. Never blocks: it only adds context.
Off when DEVKB_GUARDRAIL=0 (benchmark arms without the guardrail). Every firing is appended to
~/.claude/hooks/devkb-guardrail.log (time, session, tool, repo) so its effect can be measured.

Registered by this repository's `.claude/settings.json` (#126), and possibly also machine-wide in
`~/.claude/settings.json`: a session is reminded once, at its first code search, however many copies run.
"""
import hashlib
import json
import os
import random
import re
import shlex
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PENDING = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-pending"

REMINDER = ("devkb guardrail: this is a code search in a repository devkb serves ({repo}). For 'where is X defined', "
            "'who calls / uses X', 'what is in this file' or 'what does a change to X touch', ask devkb first "
            "(`devkb symbol|uses|outline|pack ... --project {repo}` or the mcp__devkb tools), check its answer against "
            "the source, and log the query and verdict in the task's dogfood log. grep stays right for filtering "
            "output, literal strings, and checking an edit.")
SEARCH = re.compile(r"(?:^|[;&|(]\s*|\bxargs\s+)(?:git\s+grep|grep|egrep|rg)\b")


def served_repo(path: Path) -> Path | None:
    try:
        p = path.expanduser().resolve()
    except OSError:
        return None
    cache = (Path.home() / ".cache" / "devkb").resolve()
    for d in [p, *p.parents]:
        if d == cache:
            return None
        if d.parent == cache / "cpp-corpus" or (d / ".devkb").is_dir() or (d / "devkb" / "cli.py").is_file():
            return d
    return None


def search_segments(cmd: str) -> list[str]:
    """The pipeline stages that search: a grep after `|` filters another command's output and does not count."""
    out = []
    # words inside quotes are text (a commit message, an echo), not a command: blank them before looking for a search
    cmd = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "", cmd, flags=re.S))
    for part in re.split(r"&&|\|\||;|\n", cmd):
        stages = [s.strip() for s in part.split("|")]
        if SEARCH.search(stages[0]) or any(s.startswith("xargs") and SEARCH.search(s) for s in stages[1:]):
            out.append(part)
    return out


def bash_dirs(cmd: str, cwd: Path) -> list[Path]:
    dirs = [cwd]
    try:
        words = shlex.split(cmd, comments=True, posix=True)
    except ValueError:
        words = cmd.split()
    for i, w in enumerate(words):
        if w == "cd" and i + 1 < len(words):
            dirs.insert(0, Path(words[i + 1]).expanduser() if words[i + 1].startswith(("/", "~")) else cwd / words[i + 1])
        elif w.startswith(("/", "~/")) and not w.startswith("/dev/"):
            dirs.append(Path(w))
    return dirs


def first_copy(ev: dict) -> bool:
    """True for the first copy of this hook to see this tool call; the others stay silent. Atomic (O_EXCL), so two
    copies running at once cannot both answer. Markers older than a day are cleared."""
    key = ev.get("tool_use_id") or hashlib.sha1(json.dumps([ev.get("session_id"), ev.get("tool_name"), ev.get("tool_input"),
                                                            int(time.time() // 10)], sort_keys=True).encode()).hexdigest()
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / "".join(c for c in key if c.isalnum() or c in "-_")[:80], os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    except OSError:
        return True
    if random.random() < 0.02:
        cutoff = time.time() - 86400
        for m in d.iterdir():
            try:
                if m.stat().st_mtime < cutoff:
                    m.unlink()
            except OSError:
                pass
    return True


def first_of_session(ev: dict) -> bool:
    """One reminder per session (#126 measurement: about 12 per run were ignored, so more add cost, not use)."""
    sid = "".join(c for c in str(ev.get("session_id") or "") if c.isalnum() or c in "-_")[:80]
    if not sid:
        return True
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / f"session-{sid}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    except OSError:
        return True
    return True


def bash_pattern(command: str) -> str:
    """The pattern of the first grep / rg in a command: the `-e` value, else the first word that is not an option."""
    try:
        words = shlex.split(command, comments=True)
    except ValueError:
        return ""
    for i, w in enumerate(words):
        if w in ("grep", "egrep", "rg"):
            words = words[i + 1:]
            break
    else:
        return ""
    for i, w in enumerate(words):
        if w == "-e" and i + 1 < len(words):
            return words[i + 1]
        if not w.startswith("-"):
            return w
    return ""


def single_bash_file(command: str, cwd: Path, repo: Path) -> str | None:
    """Resolve an explicit file operand for a search that requests numbered output."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None
    if words[:2] == ["git", "grep"]:
        words = words[1:]
    if not words or words[0] not in ("grep", "egrep", "rg"):
        return None
    operands = []
    has_pattern = False
    has_line_numbers = False
    after_options = False
    args = iter(words[1:])
    for word in args:
        if re.fullmatch(r"[();<>|&]+", word):
            return None
        if not after_options and word == "--":
            after_options = True
        elif not after_options and word == "-e":
            if next(args, None) is None:
                return None
            has_pattern = True
        elif not after_options and word.startswith("-"):
            # Only flags that take no argument are unambiguous here.
            if not re.fullmatch(r"-[rRnHhEFiw]+", word):
                return None
            has_line_numbers |= "n" in word
        elif not has_pattern:
            has_pattern = True
        else:
            operands.append(word)
    if not has_line_numbers or len(operands) != 1 or re.search(r"[$`*?\[\]{}~\r\n]", operands[0]):
        return None
    try:
        path = (cwd / operands[0]).resolve()
        if path.is_file():
            return path.relative_to(repo).as_posix()
    except (OSError, ValueError):
        pass
    return None


SUBSTITUTED = ("devkb answered this search from the graph: every name it asks about resolved, with coverage Complete, "
               "so this is the search's result (grep was not needed).\n\n{answers}\n\n(For grep's raw lines as well, "
               "repeat the identical command: a repeat runs as a plain search.)")
READ_ANSWER = ("devkb answered this definition search from the graph: the location as grep would print it, and the body "
               "(`devkb symbol --source`).\n\n{answers}\n\n(For grep's raw lines, repeat the identical command: a repeat "
               "runs as a plain search.)")
ALONGSIDE = ("devkb's answer for the names this search asks about (resolved, coverage Complete); the command still "
             "ran.\n\n{answers}")
MAX_ANSWER = 8000
# A search for a name is a direct-use question (#154): direct callers and the definition, not callers at any depth.
QUESTION = "refactor"


CODE_EXTS = {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp", ".py", ".js", ".jsx", ".ts",
             ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".swift", ".scala", ".lua", ".sh",
             ".m", ".mm", ".vue", ".pl", ".sql"}
DOC_TYPES = {"md", "markdown", "txt", "text", "rst", "json", "yaml", "yml", "toml", "xml", "html", "csv", "log", "tex",
             "org", "ini", "cfg", "lock", "svg", "pdf", "doc", "docx"}
WILDCARD = re.compile(r"[$`*?\[\]{}~]")


def documents_only(globs: list[str]) -> bool:
    """True when include globs leave only non-code files (`*.md`, `**/*.{md,txt}`). A glob with no extension is unknown."""
    exts: list[str] = []
    for g in globs:
        found = re.findall(r"\.([A-Za-z0-9_+]+)(?=$|[,}])", g)
        if not found:
            return False
        exts += ["." + e.lower() for e in found]
    return bool(exts) and not any(e in CODE_EXTS for e in exts)


def operand_paths(operands: list[str], cwd: Path) -> tuple[list[Path], str | None]:
    """(resolved paths, why they are not all plain directories). A wildcard operand stands for its fixed prefix."""
    paths: list[Path] = []
    why = None
    for o in operands:
        wild = bool(WILDCARD.search(o.lstrip("~")))
        if wild:
            fixed = []
            for part in o.split("/"):
                if WILDCARD.search(part.lstrip("~")):
                    break
                fixed.append(part)
            o = "/".join(fixed) or "."
            why = why or "glob-operand"
        try:
            path = Path(o).expanduser()
            path = (path if path.is_absolute() else cwd / path).resolve()
        except (OSError, RuntimeError):
            why = why or "path-unreadable"
            continue
        paths.append(path)
        if not wild and not path.is_dir():
            why = why or ("file-operand" if path.is_file() else "path-missing")
    return paths, why


def is_trim_stage(st: list[str]) -> bool:
    """`head` / `tail` with only a line count (`-n N`, `-nN`, `-N`, `--lines=N`): it shortens output, not the question."""
    if not st or st[0] not in ("head", "tail"):
        return False
    args = st[1:]
    k = 0
    while k < len(args):
        a = args[k]
        if a == "-n" and k + 1 < len(args) and re.fullmatch(r"\+?\d+", args[k + 1]):
            k += 2
        elif re.fullmatch(r"-n\+?\d+|-\d+|--lines=\+?\d+", a):
            k += 1
        else:
            return False
    return True


def bash_search(command: str, cwd: Path) -> tuple[list[Path], str | None]:
    """(the paths the shell search covers, why it is not the plain question `where is NAME used in these folders`; None
    when it is). Paths are the operands of the search stages, or the directory the search runs in when it names none."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        words = list(lexer)
    except ValueError:
        return [], "unparsable"
    stages: list[list[str]] = [[]]
    ops: list[str] = []
    for w in words:
        if re.fullmatch(r"[|&;()<>]+", w):
            if w in ("|", "||", "&&", ";", "&"):
                ops.append(w)
                stages.append([])
            else:
                ops.append("syntax")
        else:
            stages[-1].append(w)
    # `search | head -5`: every stage after the search that only trims lines is the same question (#174)
    while len(stages) > 1 and ops[-1] == "|" and is_trim_stage(stages[-1]):
        stages.pop()
        ops.pop()
    paths: list[Path] = []
    reasons: list[str] = []
    searches = 0
    here = cwd
    for i, st in enumerate(stages):
        while st and re.fullmatch(r"\w+=\S*", st[0]):
            st = st[1:]
        piped = i > 0 and ops[i - 1] == "|"
        if st[:1] == ["cd"] and len(st) > 1:
            p = Path(st[1]).expanduser()
            here = (p if p.is_absolute() else here / p)
            continue
        kind = " ".join(st[:2]) if st[:2] == ["git", "grep"] else (st[0] if st else "")
        if kind not in ("grep", "egrep", "rg", "git grep") or piped:
            continue
        searches += 1
        args = st[len(kind.split()):]
        pattern_set = recursive = after = False
        operands: list[str] = []
        globs: list[str] = []
        if kind not in ("grep", "egrep"):
            reasons.append(f"tool:{kind}")
        it = iter(args)
        for a in it:
            if not after and a == "--":
                after = True
            elif not after and a == "-e":
                if next(it, None) is None:
                    reasons.append("option:-e")
                pattern_set = True
            elif not after and (a == "--color" or a.startswith("--color=")):
                pass
            elif not after and (a.startswith("--include=") or a == "--include"):
                g = a.split("=", 1)[1] if "=" in a else next(it, "")
                globs.append(g)
            elif not after and a.startswith("--"):
                reasons.append(f"option:{a.split('=')[0]}")
            elif not after and a.startswith("-") and len(a) > 1:
                for k, c in enumerate(a[1:]):
                    if c in "rR":
                        recursive = True
                    elif c not in "nHwEF":
                        reasons.append(f"option:-{c}")
                        if c in "ABCm" and k == len(a) - 2:
                            next(it, None)       # `-A 30`: the value is the next argument, not a path (#172)
                        break
            elif not pattern_set:
                pattern_set = True
            else:
                operands.append(a)
        if kind == "rg":
            recursive = True
        if not operands:
            if recursive:
                paths.append(here.resolve())
            else:
                reasons.append("stdin")
        else:
            ps, why = operand_paths(operands, here)
            paths += ps
            if why:
                reasons.append(why)
            if not recursive and why is None:
                reasons.append("not-recursive")
        if globs and documents_only(globs):
            reasons.append("document-glob")
    if not searches:
        return [], "no-search"
    first = []
    real = [st for st in stages if st and not (st[0] == "cd" and len(st) > 1)]   # a leading `cd DIR &&` only moves
    if searches > 1 or len(real) > 1 or (len(stages) > 1 and "&&" not in ops):
        first.append("pipe" if "|" in ops else "compound")
    if "syntax" in ops:
        first.append("shell-syntax")
    reasons = first + reasons
    return paths, (reasons[0] if reasons else None)


def grep_tool_search(inp: dict, cwd: Path) -> tuple[list[Path], str | None]:
    """The same for a Grep tool call."""
    why = None
    mode = inp.get("output_mode") or "files_with_matches"       # the Grep tool's default
    if mode == "files_with_matches":
        why = "option:files"                     # a file list is the question `grep -l` asks, not a caller list
    elif mode != "content":
        why = f"output_mode:{mode}"
    elif inp.get("-i"):
        why = "option:-i"
    elif any(inp.get(k) for k in ("-A", "-B", "-C", "context")):
        why = "context"
    elif inp.get("multiline"):
        why = "multiline"
    globs = [inp["glob"]] if inp.get("glob") else []
    if why is None and ((globs and documents_only(globs)) or str(inp.get("type") or "").lower() in DOC_TYPES):
        why = "document-glob"
    paths, pwhy = operand_paths([inp["path"]] if inp.get("path") else ["."], cwd)
    return paths, why or pwhy


def repo_of(paths: list[Path]) -> tuple[Path | None, str | None]:
    """(the one repository all paths are in, why not)."""
    repos = {served_repo(p) for p in paths}
    if not paths or None in repos:
        return None, "outside-repo"
    if len(repos) > 1:
        return None, "several-repos"
    return repos.pop(), None


def scope_of(paths: list[Path], repo: Path) -> list[str] | None:
    """The repository-relative folders the search is limited to; None when it covers the whole repository."""
    out = []
    for p in paths:
        try:
            rel = p.relative_to(repo).as_posix()
        except ValueError:
            continue
        if rel == ".":
            return None
        out.append(rel)
    return out or None


def filter_pack(text: str, scope: list[str]) -> tuple[str, int]:
    """Keep the callers (and test files) under `scope`; (filtered text, callers kept). Counts in the headings follow."""
    def inside(f: str) -> bool:
        return any(f == d or f.startswith(d + "/") for d in scope)
    out, section, kept, counts = [], "", 0, {}
    for line in text.splitlines():
        if line.startswith("## "):
            section = line
        m = re.match(r"- `([^`]+)`", line)
        if m and (section.startswith("## Files with a direct caller") or section.startswith("## Test files")):
            if not inside(m.group(1)):
                continue
            counts[section[:12]] = counts.get(section[:12], 0) + 1
            kept += section.startswith("## Files with") and 1 or 0
        out.append(line)
    res = "\n".join(out)
    res = re.sub(r"(## Files with a direct caller \()\d+", lambda m: m.group(1) + str(counts.get("## Files wit", 0)), res)
    res = re.sub(r"(## Test files among them \()\d+", lambda m: m.group(1) + str(counts.get("## Test file", 0)), res)
    # a section left empty reads "none"
    res = re.sub(r"(## Test files among them \(0\)\n)(?!- none)", r"\1- none\n", res)
    return res, kept


def again(ev: dict, inp: dict) -> bool:
    """True the second time this session makes exactly this search: the agent asked for the raw matches."""
    sid = "".join(c for c in str(ev.get("session_id") or "") if c.isalnum() or c in "-_")[:80]
    key = hashlib.sha1(json.dumps([sid, ev.get("tool_name"), inp], sort_keys=True).encode()).hexdigest()
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / f"sub-{key}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return True
    except OSError:
        return True
    return False


def log_decision(ev: dict, repo: Path | str, tool: str, action: str, names: list[str], queries: list[dict], chars: int,
                 reason: str = "", scope: list[str] | None = None) -> None:
    """#149: one line per decision on a navigation search, in the guardrail log: the action, the names, their verdicts
    and the size of the answer in characters."""
    try:
        log = Path.home() / ".claude" / "hooks" / "devkb-guardrail.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as fh:
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": ev.get("session_id"), "tool": tool,
                                 "repo": str(repo), "action": action, "names": names,
                                 "verdicts": [q["verdict"] for q in queries], "chars": chars, "reason": reason,
                                 "scope": scope}) + "\n")
    except OSError:
        pass


READ_CAP = 80


def definition_answer(repo: Path, name: str, scope: list[str] | None) -> tuple[str, str] | None:
    """SPEC-DKB-006 R1-R3: (answer, reason) for a definition search, or None when the search should run. One definition in
    the searched scope: `file:line:` as grep prints it, then the body (at most READ_CAP lines; beyond that the location and
    span). Several: the locations only. A file changed since the graph was built: None."""
    from devkb import misses
    defs = misses.run_definitions(repo, name)
    if scope:
        defs = [m for m in defs or [] if any((f := m["k"].split("::", 1)[0]) == d or f.startswith(d + "/") for d in scope)]
    if not defs or any(not m.get("ls") or misses.changed_since_build(repo, m["k"].split("::", 1)[0]) for m in defs):
        return None
    where = [f"{m['k'].split('::', 1)[0]}:{m['ls']}:{m.get('sig', '')}" for m in defs]
    if len(defs) > 1:
        return (f"{len(defs)} definitions of {name}; locations only, no body (name one to read it):\n" + "\n".join(where),
                "locations")
    m = defs[0]
    f, src = m["k"].split("::", 1)[0], m.get("source") or {}
    span = f"{f} lines {m['ls']}-{m['le']}" if m.get("range") == "exact" and m.get("le") else f"{f} from line {m['ls']}"
    if src.get("lines") is None or src.get("more") or src.get("approx"):
        why = (f"longer than {READ_CAP} lines" if src.get("more") or src.get("too_long") else "its end is not known")
        return (f"{where[0]}\n(Body not shown: {name} is {why}. Span: {span}. Read the span you need.)", "over-cap")
    return (f"{where[0]}\n" + "\n".join(src["lines"]), "one-definition")


def answer_or_record(ev: dict, repo: Path, tool: str, inp: dict, pattern: str, paths: list[Path] | None = None,
                     why: str | None = None) -> dict | None:
    """#131 + #133. Ask devkb about the names the search asks for. Every name resolved and Complete: return devkb's
    answer as the result (a pure search) or beside it (a compound command), in the same call. Otherwise the search runs
    untouched, and the verdict is kept for the PostToolUse hook, which logs the miss if grep finds code."""
    from devkb import misses
    key = "".join(c for c in str(ev.get("tool_use_id") or "") if c.isalnum() or c in "-_")[:80]
    names = misses.navigation_names(pattern)
    if not names or not (repo / ".devkb").is_dir():
        return None
    if why == "document-glob":                   # the graph holds no document text: an answer would only add tokens
        log_decision(ev, repo, tool, "pass-through", names, [], 0, why)
        return None
    dname = misses.definition_name(pattern)
    # a definition search asks where X is defined and what it says: recursive or not, in one file or a folder, and with
    # context lines (`-A30`), which are the agent reading the body (#166 clarification)
    lenient = bool(dname) and why in ("not-recursive", "file-operand", "option:-A", "option:-B", "option:-C", "context")
    if lenient:
        why = None
    queries, answers = [], []
    for n in names:
        r = misses.run_query(repo, QUESTION, n)
        if r:
            queries.append({"name": n, "verdict": r[0], "detail": r[1],
                            "query": f"devkb pack {QUESTION} {shlex.quote(n)} --project {shlex.quote(str(repo))}"})
            answers.append(r[2].strip())
    if dname and why is None:
        scope = scope_of(paths or [], repo)
        ans = definition_answer(repo, dname, scope)
        if ans:                                  # one name, found in the graph: the answer does not need the caller pack
            if again(ev, inp):
                log_decision(ev, repo, tool, "repeat", names, queries, len(ans[0]), "repeat", scope)
                return None
            log_decision(ev, repo, tool, "read-answer", names, queries, len(ans[0]), f"definition:{ans[1]}", scope)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": READ_ANSWER.format(answers=ans[0])}}
    if lenient:
        log_decision(ev, repo, tool, "pass-through", names, queries, 0, "not-recursive")
        return None
    if queries and len(queries) == len(names) and all(q["verdict"] == "complete" for q in queries):
        text = "\n\n".join(answers)
        text = text if len(text) <= MAX_ANSWER else text[:MAX_ANSWER].rsplit("\n", 1)[0] + "\n... (cut)"
        scope = scope_of(paths or [], repo)
        if why is None and scope:                # narrower than the repository: the answer is filtered to the folders
            filtered = [filter_pack(a, scope) for a in answers]
            if not all(k for _, k in filtered):
                log_decision(ev, repo, tool, "pass-through", names, queries, 0, "nothing-in-scope", scope)
                return None
            text = "\n\n".join(a for a, _ in filtered)
            text = f"(Filtered to {', '.join(d + '/' for d in scope)}: callers elsewhere are left out.)\n\n" + text
        if why is None:
            if again(ev, inp):
                log_decision(ev, repo, tool, "repeat", names, queries, len(text), "repeat", scope)
                return None                      # the agent asked for the raw matches: let the search run
            log_decision(ev, repo, tool, "substitute", names, queries, len(text), "same-question", scope)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": SUBSTITUTED.format(answers=text)}}
        log_decision(ev, repo, tool, "alongside", names, queries, len(text), why)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ALONGSIDE.format(answers=text)}}
    log_decision(ev, repo, tool, "pass-through", names, queries, 0, "not-complete")
    if not misses.enabled() or not key or not any(q["verdict"] not in ("complete", "other") for q in queries):
        return None
    built, head = misses.graph_state(repo)
    single_file = None
    if tool == "Bash":
        cwd = Path(ev.get("cwd") or os.getcwd())
        single_file = single_bash_file(inp.get("command", ""), cwd, repo)
    try:
        PENDING.mkdir(parents=True, exist_ok=True)
        (PENDING / key).write_text(json.dumps({
            "repo": str(repo), "session": ev.get("session_id") or "", "tool": tool, "pattern": pattern, "names": names,
            "queries": queries, "built": built, "head": head, "version": misses.devkb_version(),
            "single_file": single_file}))
    except OSError:
        pass
    return None


def main() -> int:
    if os.environ.get("DEVKB_GUARDRAIL", "1") == "0":
        return 0
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input") or {}
    cwd = Path(ev.get("cwd") or os.getcwd())
    pattern = ""
    if tool == "Grep":
        pattern = inp.get("pattern", "")
        paths, why = grep_tool_search(inp, cwd)
    elif tool == "Bash":
        if not search_segments(inp.get("command", "")):
            return 0
        pattern = bash_pattern(inp.get("command", ""))
        paths, why = bash_search(inp.get("command", ""), cwd)
        if not paths:                            # a form the parser does not read (xargs ...): fall back to what it names
            paths = [d for s in search_segments(inp["command"]) for d in bash_dirs(s, cwd)][:1] or [cwd]
            why = why or "unread-form"
    else:
        return 0
    repo, outside = repo_of(paths)
    if repo is None:
        return 0                                 # not one devkb repository: the search is not ours to answer
    if not first_copy(ev):
        return 0
    try:
        out = answer_or_record(ev, repo, tool, inp, pattern, paths, why)
    except Exception:  # noqa: BLE001  devkb must never get in the search's way
        out = None
    if out:
        print(json.dumps(out))
        return 0
    if not first_of_session(ev):
        return 0
    try:
        with open(Path.home() / ".claude" / "hooks" / "devkb-guardrail.log", "a") as fh:
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": ev.get("session_id"),
                                 "tool": tool, "repo": str(repo), "action": "remind"}) + "\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": REMINDER.format(repo=repo)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
