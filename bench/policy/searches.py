"""What an agent's tool calls were, read from a recorded stream: the searches it ran and whether a call wrote code. One parser for the
replay scripts, so that they count the same things (an audit found three different ones, each missing some calls).

  searches_in(name, input)  the patterns of every grep/rg/egrep/git grep in a Bash command and of the Grep tool: in a pipeline, a chain, a
                            subshell, `$(...)`, `if grep ...`, behind `xargs`/`timeout`/`command`/`sudo`/`env`, or as `find -exec grep`;
                            options and their values skipped; every `-e`; `--` ends the options; a heredoc body is text, not a command
  writes_code(name, input)  an Edit/Write/MultiEdit/NotebookEdit call on a source or document file, or a Bash command that writes one:
                            `sed -i`, a redirect to a file (not /dev/null or /tmp), `tee`, `git apply`, `patch`, `cat >`, `write_text(`,
                            or an `open(..., 'w')`; quoted text is ignored, so `awk '$1 > 3'` is not a write
"""
from __future__ import annotations

import re
import shlex

_GREPS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
_VALUE_OPTS = {
    "grep": {"-A", "-B", "-C", "-m", "-f", "-d", "-D", "--include", "--exclude", "--exclude-dir", "--exclude-from", "--include-dir", "--label",
             "--binary-files", "--max-count", "--file", "--context", "--after-context", "--before-context", "--devices", "--directories"},
    "rg": {"-g", "--glob", "-t", "--type", "-T", "--type-not", "-j", "--threads", "-m", "--max-count", "-A", "-B", "-C", "--max-depth", "-d",
           "--maxdepth", "--max-filesize", "-E", "--encoding", "-M", "--max-columns", "--sort", "--sortr", "-f", "--file", "--context",
           "--after-context", "--before-context", "--iglob", "--ignore-file", "--path-separator", "--pre", "--pre-glob", "-r", "--replace",
           "--color", "--colors", "--dfa-size-limit", "--regex-size-limit", "--engine", "--type-add", "--type-clear"},
}
_VALUE_OPTS["egrep"] = _VALUE_OPTS["fgrep"] = _VALUE_OPTS["ag"] = _VALUE_OPTS["ack"] = _VALUE_OPTS["grep"]
_PREFIX = {"if", "then", "do", "else", "elif", "while", "until", "time", "command", "exec", "nohup", "sudo", "env", "nice", "ionice", "stdbuf", "!", "builtin"}
_CODE = (".py", ".pyi", ".h", ".hh", ".hpp", ".c", ".cc", ".cpp", ".cxx", ".ts", ".tsx", ".js", ".jsx", ".sh", ".go", ".rs", ".java", ".rb", ".cs",
         ".md", ".rst", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html", ".css")
_EXT = "py|pyi|h|hh|hpp|c|cc|cpp|cxx|ts|tsx|js|jsx|sh|go|rs|java|rb|cs|md|rst|json|yml|yaml|toml|cfg|ini|html|css"


def _strip_heredocs(command: str) -> str:
    """The command with the bodies of its here-documents removed: they are text fed to a program, not commands."""
    return re.sub(r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n.*?\n[ \t]*\1[ \t]*(?:\n|$)", r"\2\n", command, flags=re.S)


def _segments(command: str) -> list[str]:
    """The simple commands of a chain: split at `;`, `&&`, `||`, `|`, newlines, parentheses and backticks, outside quotes."""
    command = _strip_heredocs(command.replace("\\\n", " "))
    out, cur, q, i = [], "", "", 0
    while i < len(command):
        c = command[i]
        if q:
            cur += c
            if c == q and command[i - 1] != "\\":
                q = ""
        elif c in "'\"":
            q, cur = c, cur + c
        elif command.startswith(("&&", "||"), i):
            out.append(cur)
            cur, i = "", i + 1
        elif c in ";|\n()`":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [x.strip().rstrip("$").strip() for x in out if x.strip().rstrip("$").strip()]


def _command_tokens(toks: list[str]) -> list[str]:
    """The tokens from the command word on: environment assignments, `cd X`, and wrappers (`timeout 10`, `xargs -n1`, `if`, `sudo`...) skipped."""
    while toks:
        t = toks[0]
        if re.fullmatch(r"[A-Za-z_]\w*=\S*", t) or t in _PREFIX:
            toks = toks[1:]
        elif t == "timeout":
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or re.fullmatch(r"\d+(\.\d+)?[smhd]?", toks[0])):
                toks = toks[1:]
        elif t == "xargs":
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                toks = toks[2:] if toks[0] in ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a") else toks[1:]
        else:
            break
    return toks


def _grep_from(toks: list[str]) -> list[str]:
    if not toks:
        return []
    cmd = toks[0].split("/")[-1]
    if cmd == "git" and len(toks) > 1 and toks[1] == "grep":
        toks, cmd = toks[1:], "grep"
    if cmd not in _GREPS:
        return []
    values = _VALUE_OPTS.get("rg" if cmd == "rg" else "grep", set())
    pats, positional, i, dd = [], [], 1, False
    while i < len(toks):
        t = toks[i]
        if dd:
            positional.append(t)
        elif t == "--":
            dd = True
        elif t in ("-e", "--regexp") and i + 1 < len(toks):
            pats.append(toks[i + 1])
            i += 1
        elif t.startswith("--regexp="):
            pats.append(t.split("=", 1)[1])
        elif t.startswith("--") and "=" in t:
            pass
        elif t in values:
            i += 1
        elif t.startswith("-") and len(t) > 1:
            if re.fullmatch(r"-[A-Za-z]*e", t) and i + 1 < len(toks):          # a cluster ending in e: `-rne PATTERN`
                pats.append(toks[i + 1])
                i += 1
            elif re.fullmatch(r"-e.+", t):
                pats.append(t[2:])
        else:
            positional.append(t)
        i += 1
    return pats or positional[:1]


def grep_patterns(command: str) -> list[str]:
    pats = []
    for seg in _segments(command):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        toks = _command_tokens(toks)
        while toks and toks[0] == "cd":
            toks = _command_tokens(toks[2:])
        if toks and toks[0] == "find":                                          # find ... -exec grep ... {} +
            for k, t in enumerate(toks):
                if t in ("-exec", "-execdir", "-ok"):
                    end = next((j for j in range(k + 1, len(toks)) if toks[j] in (";", "+")), len(toks))
                    pats += _grep_from([x for x in toks[k + 1:end] if x != "{}"])
            continue
        pats += _grep_from(toks)
    return pats


def searches_in(name: str, inp: dict) -> list[str]:
    if name == "Grep":
        return [inp["pattern"]] if inp.get("pattern") else []
    if name == "Bash":
        return grep_patterns(inp.get("command", "") or "")
    return []


_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_REDIRECT = re.compile(rf"(?<![<>\d&=-])>{{1,2}}\s*(?!/dev/|/tmp/|&)[\w./~$-]+\.(?:{_EXT})\b")
_BASH_WRITE = re.compile(r"\bsed\s+(-[A-Za-z]*i|--in-place)|\btee\s+(-a\s+)?[\w./~-]+\.(?:" + _EXT + r")\b|\bgit\s+apply\b|\bpatch\s+-|\bcat\s*>>?\s*[\w./~-]+")
_PY_WRITE = re.compile(r"\.write_text\(|open\([^)]*,\s*['\"][wax]\+?b?['\"]")


def writes_code(name: str, inp: dict) -> bool:
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return str(inp.get("file_path", "")).endswith(_CODE)
    if name == "Bash":
        raw = inp.get("command", "") or ""
        if re.match(r"\s*(?:python3?\s+-m\s+)?pytest\b", raw):
            return False
        bare = _QUOTED.sub("''", _strip_heredocs(raw))                          # a `>` inside quotes (awk '$1 > 3') is not a redirect
        return bool(_BASH_WRITE.search(bare) or _REDIRECT.search(bare) or _PY_WRITE.search(raw))
    return False
