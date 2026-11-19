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
import subprocess
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
    skip = False
    for i, w in enumerate(words):
        if skip:                                 # the value of an option that takes one (#215): never the pattern
            skip = False
            continue
        if w == "-e" and i + 1 < len(words):
            es = [words[j + 1] for j in range(i, len(words) - 1) if words[j] == "-e"]
            return "\\|".join(es)              # every -e is part of the question (#185)
        if w in VALUE_OPTIONS or (re.fullmatch(r"-[A-Za-z]*[ABCmtgT]", w) and not w.startswith("--")):
            skip = True
            continue
        if not w.startswith("-"):
            return w
    return ""


VALUE_OPTIONS = {"--include", "--exclude", "--exclude-dir", "--type", "-t", "--glob", "-g", "--max-count", "-m",
                 "--after-context", "--before-context", "--context", "-A", "-B", "-C", "--type-not", "-T", "-f", "--file"}


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


KEYWORDS = {"def", "class", "struct", "enum", "union", "interface", "fn", "func", "function", "void", "static", "inline",
            "virtual", "async", "public", "private", "protected", "pub"}


def classify(tool: str, inp: dict, pattern: str, why: str | None, paths: list[Path] | None = None) -> str:
    """What a search asks (SPEC-DKB-007 §3.2), from the whole search: pattern, flags, operands, pipes and the tool; the
    names alone never decide it (#214). First match wins. It reads no graph and changes no answer."""
    from devkb import misses
    cmd = inp.get("command", "") if tool == "Bash" else ""
    why = why or ""
    bare = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", cmd)     # quoted text cannot hold an option or a pipe
    first = bare.split("|", 1)[0]
    ctx = (tool == "Grep" and any(inp.get(k) for k in ("-A", "-B", "-C", "context"))) or \
        bool(re.search(r"(?:^|\s)-(?:[A-Za-z]*[ABC]\s*\d|-(?:after|before)?-?context)", first))
    words = re.findall(r"[A-Za-z_][\w.:]*", re.sub(r"\\[sbdwSBDW<>]", " ", pattern))
    flags = search_flags(tool, inp)              # every option of the search, not only the parser's first reason (#180)
    if flags & {"c", "count"}:
        return "count"
    if flags & {"l", "L", "files"}:
        return "list-files"
    if flags & {"v"}:
        return "invert"
    if why == "document-glob" or (paths and all(p.is_file() and p.suffix.lower() not in CODE_EXTS for p in paths)):
        return "non-code"                         # documents, or named files that hold no code (`.gitignore`, `*.md`)
    if why in ("option:-c",) or why.startswith("output_mode:count") or re.search(r"\|\s*wc\b", cmd):
        return "count"
    if why in ("option:-l", "option:-L", "option:files") or why.startswith("output_mode:files"):
        return "list-files"
    if why == "option:-v":
        return "invert"
    if words and all(w in KEYWORDS for w in words):
        return "list-symbols"                     # `^def `, `"    def "`, `^def \|^class `: a file's definitions
    filt = [f for opts, _q, f in re.findall(r"\|\s*(?:e|f)?grep\s+((?:-\S+\s+)*)(['\"])(.*?)\2", cmd) if "v" not in opts]
    for fw in (re.findall(r"[A-Za-z_]\w*", f) for f in filt):
        if fw and all(w in KEYWORDS for w in fw):
            return "list-symbols"                 # `grep X file | grep "def \|class "`: the definitions that mention X
        if fw and fw[0] in KEYWORDS and len(fw) > 1:
            return "locate"                       # `grep X | grep "def X"`: where X is defined
    defn = misses.definition_name(pattern) or (misses.navigation_names(pattern)
                                                and re.search(r"(?<![\w])(?:def|class|struct|fn|function)(?:\s|\\s)", pattern))
    if defn:
        return "read-body" if ctx else "locate"
    if ctx and misses.navigation_names(pattern):
        return "read-body"                        # the lines around a name: the body it sits in
    if re.match(r"\^\s*(?:\\s\*)?[A-Za-z_]", pattern):
        return "locate"                           # a name anchored at line start: where it is defined
    if not misses.navigation_names(pattern):
        return "literal"
    if why in ("file-operand", "not-recursive") or (paths and all(p.is_file() for p in paths)):
        return "in-file"                          # a search confined to named files, whatever its other flags
    if why == "pipe" and re.search(r"\|\s*(?:e|f)?grep\b", cmd):
        return "call-sites-filtered"
    if why in ("", "pipe", "compound", "option:-i", "context", "glob-operand"):
        return "call-sites"
    return "unknown"


def resolved_name(pack: str) -> str | None:
    """The short name of the symbol a pack resolved (`pkg/core.py::Store.put` gives `put`)."""
    m = re.search(r"changing the signature of `([^`]+)`", pack)
    return re.split(r"::|\.", m.group(1))[-1] if m else None


def same_case(name: str, pack: str) -> bool:
    """The pack answers for the name as written, case included (#184, #215): its resolved key's last component is the
    searched name's last component. devkb's resolver also matches other cases, which a case-sensitive grep never does."""
    m = re.search(r"changing the signature of `([^`]+)`", pack)
    if not m:
        return True
    last = lambda k: re.split(r"::|\.", k)[-1]
    return last(m.group(1)) == last(name)


def dialect_of(tool: str, inp: dict) -> tuple[str, bool]:
    """(alternation dialect, case-insensitive) of the search: grep is a basic regex unless -E/-P (or egrep), -F is a
    fixed string; rg, git grep -E and the Grep tool are extended."""
    if tool == "Grep":
        return "ere", bool(inp.get("-i"))
    try:
        words = shlex.split(inp.get("command", ""), comments=True)
    except ValueError:
        return "both", False
    for i, w in enumerate(words):
        if w in ("grep", "egrep", "fgrep", "rg"):
            flags = "".join(x[1:] for x in words[i + 1:] if x.startswith("-") and not x.startswith("--"))
            longs = [x for x in words[i + 1:] if x.startswith("--")]
            nocase = "i" in flags or "--ignore-case" in longs or (w == "rg" and ("S" in flags or "--smart-case" in longs))
            if w == "fgrep" or "F" in flags or "--fixed-strings" in longs:
                return "fixed", nocase
            if w in ("egrep", "rg") or "E" in flags or "P" in flags or "--extended-regexp" in longs:
                return "ere", nocase
            return "bre", nocase
    return "both", False


def search_flags(tool: str, inp: dict) -> set[str]:
    """The output-changing options of the first search: c (count), l/L (file names), v (invert), as letters."""
    if tool == "Grep":
        mode = inp.get("output_mode", "files_with_matches")
        return {"count"} if mode == "count" else {"files"} if mode == "files_with_matches" else set()
    try:
        words = shlex.split(inp.get("command", ""), comments=True)
    except ValueError:
        return set()
    out: set[str] = set()
    start = next((i for i, x in enumerate(words) if x in ("grep", "egrep", "fgrep", "rg")), None)
    if start is None:
        return out
    skip = False
    for x in words[start + 1:]:
        if x == "|":
            break
        if skip:
            skip = False
            continue
        if x in ("--count",):
            out.add("c")
        elif x in ("--files-with-matches", "--files-without-match"):
            out.add("l")
        elif x == "--invert-match":
            out.add("v")
        elif re.fullmatch(r"-[A-Za-z0-9]+", x):
            for ch in re.sub(r"[ABCm]\d*$", "", x[1:]):
                if ch in "clLv":
                    out.add(ch)
            skip = bool(re.search(r"[ABCmef]$", x))
    return out


def question_of(action: str, queries: list[dict]) -> str:
    """The graph question the hook asked for this decision."""
    if action == "read-answer":
        return "symbol --source"
    if action == "span-hint":
        return "outline"
    return f"pack {QUESTION}" if queries else "none"


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
                                 "scope": scope, "intent": ev.get("_intent", "unknown"),
                                 "question": question_of(action, queries)}) + "\n")
    except OSError:
        pass


READ_CAP = 80


def definition_answer(repo: Path, name: str, scope: list[str] | None, globs: list[str] | None = None) -> tuple[str, str] | None:
    """SPEC-DKB-006 R1-R3: (answer, reason) for a definition search, or None when the search should run. One definition in
    the searched scope: `file:line:` as grep prints it, then the body (at most READ_CAP lines; beyond that the location and
    span). Several: the locations only. A file changed since the graph was built: None."""
    from devkb import misses
    defs = misses.run_definitions(repo, name)
    if scope:
        defs = [m for m in defs or [] if any((f := m["k"].split("::", 1)[0]) == d or f.startswith(d + "/") for d in scope)]
    if globs:                                    # --include / glob / type: only the files the search admits (#181)
        import fnmatch
        defs = [m for m in defs or [] if any(fnmatch.fnmatch((f := m["k"].split("::", 1)[0]), g) or fnmatch.fnmatch(Path(f).name, g)
                                              for g in globs)]
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


NO_ANSWER = {"count", "list-files", "invert", "literal", "non-code", "not-a-search", "unknown"}   # §3.3: no graph question
LINES_CAP = 60


def read_tool(repo: Path, *args: str) -> dict | None:
    """One read tool's --json answer (`uses`, `outline`), or None."""
    from devkb import misses
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONWARNINGS="ignore",
               DEVKB_TELEMETRY="0")
    try:
        p = subprocess.run(misses.devkb_command(repo, *args, "--json"), cwd=repo, env=env, capture_output=True, text=True,
                           timeout=12)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def use_lines(repo: Path, names: list[str]) -> list[tuple[str, int, str]] | None:
    """(file, line, text) of every line that uses one of the names, as grep prints them, from `uses --json`."""
    out = []
    for n in names:
        r = read_tool(repo, "uses", n)
        if r is None:
            return None
        out += [(f["f"], h["line"], h["text"]) for f in r.get("files", []) for h in f.get("hits", [])]
    return sorted(set(out))


def pipe_filters(cmd: str) -> list[tuple[bool, re.Pattern]] | None:
    """The `| grep [-v] PAT` stages after the search, as (inverted, regex); None when a stage is not a grep filter."""
    stages = [x.strip() for x in re.split(r"(?<!\\)\|(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)", cmd)][1:]
    out = []
    for st in stages:
        if is_trim_stage(shlex.split(st)) if st else False:
            continue
        try:
            w = shlex.split(st)
        except ValueError:
            return None
        if not w or w[0] not in ("grep", "egrep"):
            return None
        flags = "".join(x[1:] for x in w[1:] if x.startswith("-") and not x.startswith("--"))
        pats = [x for x in w[1:] if not x.startswith("-")]
        if not pats:
            return None
        pat = pats[0] if "E" in flags or w[0] == "egrep" else pats[0].replace("\\|", "|").replace("\\(", "(").replace("\\)", ")")
        try:
            out.append(("v" in flags, re.compile(re.escape(pats[0]) if "F" in flags else pat, re.I if "i" in flags else 0)))
        except re.error:
            return None
    return out


def lines_text(rows: list[tuple[str, int, str]], one_file: bool = False) -> str:
    shown = rows[:LINES_CAP]
    text = "\n".join(f"{ln}:{t}" if one_file else f"{f}:{ln}:{t}" for f, ln, t in shown)
    return text + (f"\n... {len(rows) - LINES_CAP} more lines" if len(rows) > LINES_CAP else "")


def locations(repo: Path, names: list[str], scope: list[str] | None) -> str | None:
    """`file:line: signature` of every definition of the names (§3.3 `locate`)."""
    from devkb import misses
    rows = []
    for n in names:
        defs = misses.run_definitions(repo, n) or []
        if scope:
            defs = [m for m in defs if any((f := m["k"].split("::", 1)[0]) == d or f.startswith(d + "/") for d in scope)]
        rows += [f"{m['k'].split('::', 1)[0]}:{m['ls']}:{m.get('sig', '')}" for m in defs if m.get("ls")]
    return "\n".join(rows) or None


def outline_answer(repo: Path, paths: list[Path] | None) -> str | None:
    """`Lstart-Lend kind name` for the one code file a definitions listing searches (§3.3 `list-symbols`)."""
    from devkb import misses
    files = [p for p in paths or [] if p.is_file()]
    if len(files) != 1:
        return None
    rel = str(files[0].resolve().relative_to(repo))
    if misses.changed_since_build(repo, rel):
        return None
    r = read_tool(repo, "outline", rel)
    if not r or not r.get("symbols"):
        return None
    return "\n".join(f"L{s['ls']}-{s['le']} {s['kind']} {s['q']}" for s in r["symbols"])


TYPE_GLOBS = {"py": ["*.py"], "python": ["*.py"], "js": ["*.js", "*.jsx", "*.mjs", "*.cjs"], "ts": ["*.ts", "*.tsx"],
              "go": ["*.go"], "rust": ["*.rs"], "rs": ["*.rs"], "java": ["*.java"], "c": ["*.c", "*.h"],
              "cpp": ["*.cc", "*.cpp", "*.cxx", "*.hpp", "*.hh", "*.h"], "cs": ["*.cs"], "csharp": ["*.cs"], "rb": ["*.rb"],
              "ruby": ["*.rb"], "php": ["*.php"], "kotlin": ["*.kt"], "swift": ["*.swift"]}


def search_globs(tool: str, inp: dict) -> list[str]:
    """The file globs a search is limited to: --include / rg -g / -t, or the Grep tool's glob / type (#181)."""
    if tool == "Grep":
        out = [g for g in re.split(r"[,\s]+", inp.get("glob") or "") if g]
        return out + TYPE_GLOBS.get(str(inp.get("type") or ""), [f"*.{inp['type']}"] if inp.get("type") else [])
    try:
        w = shlex.split(inp.get("command", ""), comments=True)
    except ValueError:
        return []
    out = []
    for i, x in enumerate(w):
        if x.startswith("--include="):
            out.append(x.split("=", 1)[1])
        elif x in ("--include", "-g", "--glob") and i + 1 < len(w) and not w[i + 1].startswith("!"):
            out.append(w[i + 1])
        elif x in ("-t", "--type") and i + 1 < len(w):
            out += TYPE_GLOBS.get(w[i + 1], [f"*.{w[i + 1]}"])
    return out


def shaped_answer(intent: str, repo: Path, names: list[str], inp: dict, paths: list[Path] | None,
                  scope: list[str] | None, tool: str = "Bash") -> str | None:
    """The answer to the question the search asks (SPEC-DKB-007 §3.3), or None: then nothing is added."""
    import fnmatch
    globs = search_globs(tool, inp)
    admit = (lambda f: any(fnmatch.fnmatch(Path(f).name, g) or fnmatch.fnmatch(f, g) for g in globs)) if globs else (lambda f: True)
    if intent == "locate":
        text = locations(repo, names, scope)
        return "\n".join(l for l in (text or "").splitlines() if admit(l.split(":", 1)[0])) or None
    rows = use_lines(repo, names)
    if rows is None:
        return None
    rows = [r for r in rows if admit(r[0])]
    if scope:
        rows = [r for r in rows if any(r[0] == d or r[0].startswith(d + "/") for d in scope)]
    if intent == "in-file":
        files = {str(p.resolve().relative_to(repo)) for p in paths or [] if p.is_file()}
        rows = [r for r in rows if r[0] in files]
        return lines_text(rows, one_file=len(files) == 1) if rows else None
    if intent == "call-sites-filtered":
        filt = pipe_filters(inp.get("command", ""))
        if filt is None:
            return None
        def kept(r):                              # grep prints `./f` for a search of `.`: a filter may expect either
            return all(any(bool(rx.search(f"{pre}{r[0]}:{r[1]}:{r[2]}")) for pre in ("", "./")) != inv
                       if not inv else not any(rx.search(f"{pre}{r[0]}:{r[1]}:{r[2]}") for pre in ("", "./"))
                       for inv, rx in filt)
        rows = [r for r in rows if kept(r)]
    return lines_text(rows) if rows else None


def answer_or_record(ev: dict, repo: Path, tool: str, inp: dict, pattern: str, paths: list[Path] | None = None,
                     why: str | None = None) -> dict | None:
    """#131 + #133. Ask devkb about the names the search asks for. Every name resolved and Complete: return devkb's
    answer as the result (a pure search) or beside it (a compound command), in the same call. Otherwise the search runs
    untouched, and the verdict is kept for the PostToolUse hook, which logs the miss if grep finds code."""
    from devkb import misses
    key = "".join(c for c in str(ev.get("tool_use_id") or "") if c.isalnum() or c in "-_")[:80]
    intent = ev.get("_intent", "unknown")
    names = misses.navigation_names(pattern, ev.get("_dialect", "both"))
    if intent == "list-symbols" and (repo / ".devkb").is_dir():   # a file's definitions: its outline, not a pack
        ans = outline_answer(repo, paths)
        if ans:
            log_decision(ev, repo, tool, "alongside", names, [], len(ans), "outline")
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ALONGSIDE.format(answers=ans)}}
        return None
    if not names or not (repo / ".devkb").is_dir():
        return None
    if intent in NO_ANSWER:                       # counts, file lists, inverted and literal searches: no graph question
        log_decision(ev, repo, tool, "pass-through", names, [], 0, why if why == "document-glob" else f"intent:{intent}")
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
        if r and r[0] == "complete" and not ev.get("_nocase") and not same_case(n, r[2]):
            r = ("other-case", f"devkb resolved {n!r} to a symbol spelled differently; grep is case-sensitive", "")
        if r:
            queries.append({"name": n, "verdict": r[0], "detail": r[1],
                            "query": f"devkb pack {QUESTION} {shlex.quote(n)} --project {shlex.quote(str(repo))}"})
            answers.append(r[2].strip())
    if dname and why is None:
        scope = scope_of(paths or [], repo)
        ans = definition_answer(repo, dname, scope, search_globs(tool, inp))
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
        scope = scope_of(paths or [], repo)
        if intent == "read-body" and len(names) == 1:     # the lines around a name: the body it is defined in
            ans = definition_answer(repo, names[0], scope, search_globs(tool, inp))
            if ans:
                log_decision(ev, repo, tool, "alongside", names, queries, len(ans[0]), f"body:{ans[1]}", scope)
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ALONGSIDE.format(answers=ans[0])}}
        found = [resolved_name(a) or n for n, a in zip(names, answers)] if ev.get("_nocase") else names
        text = shaped_answer(intent, repo, found, inp, paths, scope, tool)
        if not text:                             # nothing in the searched scope: grep may still find a mention there
            log_decision(ev, repo, tool, "pass-through", names, queries, 0, "nothing-in-scope", scope)
            return None
        text = text if len(text) <= MAX_ANSWER else text[:MAX_ANSWER].rsplit("\n", 1)[0] + "\n... (cut)"
        if why is None and intent != "call-sites":
            why = f"intent:{intent}"                # only a repository- or folder-wide name search is replaced
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

SED_READ = re.compile(r"""^\s*sed\s+-n\s+(['"]?)(\d+),(\d+)p\1\s+(\S+)\s*$""")
HEAD_READ = re.compile(r"^\s*head\s+(?:-n\s*|-)(\d+)\s+(\S+)\s*$")
TAIL_READ = re.compile(r"^\s*tail\s+-n\s*\+(\d+)\s+(\S+)\s*$")


def read_range(tool: str, inp: dict) -> tuple[str, int, int | None] | None:
    """SPEC-DKB-006 R4: (file, first line, last line or None for to the end) of a read of a line range, or None."""
    if tool == "Read":
        f, off, lim = inp.get("file_path"), inp.get("offset"), inp.get("limit")
        if not f or not (off or lim):
            return None
        try:
            a = max(1, int(off or 1))
            return f, a, a + int(lim) - 1 if lim else None
        except (TypeError, ValueError):
            return None
    if tool != "Bash":
        return None
    cmd = inp.get("command", "")
    if m := SED_READ.match(cmd):
        return m.group(4), int(m.group(2)), int(m.group(3))
    if m := HEAD_READ.match(cmd):
        return m.group(2), 1, int(m.group(1))
    if m := TAIL_READ.match(cmd):
        return m.group(2), int(m.group(1)), None
    return None


def span_hint(ev: dict, tool: str, inp: dict) -> dict | None:
    """SPEC-DKB-006 R4-R6: a read that starts inside a function or class and stops before its end gets one line with the
    full span. Never blocks; once per file and range per session; nothing for a file changed since the build."""
    rng = read_range(tool, inp)
    if not rng or rng[2] is None:
        return None
    f, a, b = rng
    cwd = Path(ev.get("cwd") or os.getcwd())
    path = Path(f).expanduser()
    path = path if path.is_absolute() else cwd / path
    repo = served_repo(path.parent)
    if repo is None or not (repo / ".devkb").is_dir():
        return None
    from devkb import misses
    try:
        rel = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None
    if not path.is_file() or misses.changed_since_build(repo, rel):
        return None
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONWARNINGS="ignore",
               DEVKB_TELEMETRY="0")
    import subprocess
    try:
        p = subprocess.run(misses.devkb_command(repo, "outline", rel, "--json", "--limit", "5000"), cwd=repo, env=env,
                           capture_output=True, text=True, timeout=12)
        syms = json.loads(p.stdout).get("symbols") or [] if p.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    inside = [s for s in syms if s.get("range") == "exact" and s.get("ls") and s.get("le")
              and s["kind"] in ("function", "method", "class") and s["ls"] <= a <= s["le"]]
    if not inside:
        return None
    s = min(inside, key=lambda x: x["le"] - x["ls"])
    if b >= s["le"]:
        return None
    sid = "".join(c for c in str(ev.get("session_id") or "") if c.isalnum() or c in "-_")[:80]
    key = hashlib.sha1(json.dumps([sid, rel, a, b]).encode()).hexdigest()
    d = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-seen"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.close(os.open(d / f"span-{key}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return None
    except OSError:
        pass
    msg = f"this range stops at L{b}; {s['q']} runs L{s['ls']}\u2013L{s['le']}"
    log_decision(ev, repo, tool, "span-hint", [s["q"]], [], len(msg), f"{rel}:{a}-{b}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}


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
    if tool == "Read" or (tool == "Bash" and read_range(tool, inp)):
        try:
            out = span_hint(ev, tool, inp) if first_copy(ev) else None
        except Exception:  # noqa: BLE001  a hint must never get in the read's way
            out = None
        if out:
            print(json.dumps(out))
        return 0
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
    try:
        ev["_intent"] = classify(tool, inp, pattern, why, paths)
    except Exception:  # noqa: BLE001  classifying is for the log only
        ev["_intent"] = "unknown"
    ev["_dialect"], ev["_nocase"] = dialect_of(tool, inp)
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
                                 "tool": tool, "repo": str(repo), "action": "remind",
                                 "intent": ev.get("_intent", "unknown")}) + "\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": REMINDER.format(repo=repo)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
