"""What an agent's tool calls were, read from a recorded stream: the searches it ran and whether a call wrote code. One parser for the
replay scripts, so that they count the same things (an audit found three different ones, each missing some calls).

  searches_in(name, input)  the patterns of every grep/rg/egrep in a Bash command (quoted or not, in any position of a pipeline or
                            chain; flags and their values skipped) and of the Grep tool
  writes_code(name, input)  an Edit/Write/MultiEdit/NotebookEdit call, or a Bash command that writes a file: `sed -i`, a redirect, `tee`,
                            `git apply`, `patch`, or a python/heredoc that opens a file for writing
"""
from __future__ import annotations

import re
import shlex

_GREPS = ("grep", "egrep", "fgrep", "rg")
_WITH_VALUE = {"-A", "-B", "-C", "-m", "-g", "-t", "-T", "-f", "--include", "--exclude", "--max-count", "--glob", "--type", "-d", "--color",
               "--context", "--after-context", "--before-context"}
_CODE = (".py", ".h", ".hh", ".hpp", ".c", ".cc", ".cpp", ".cxx", ".ts", ".tsx", ".js", ".sh", ".md", ".json", ".yml", ".yaml", ".toml")


def _segments(command: str) -> list[str]:
    """The simple commands of a chain: split at `;`, `&&`, `||`, `|` and newlines, outside quotes."""
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
        elif c in ";|\n":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def grep_patterns(command: str) -> list[str]:
    pats = []
    for seg in _segments(command):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and (re.fullmatch(r"[A-Za-z_]\w*=\S*", toks[0]) or toks[0] in ("cd", "time", "sudo", "env")):
            toks = toks[2:] if toks[0] == "cd" else toks[1:]
        if not toks or toks[0].split("/")[-1] not in _GREPS:
            continue
        i, pat = 1, None
        while i < len(toks):
            t = toks[i]
            if t == "-e" and i + 1 < len(toks):
                pat = toks[i + 1]
                break
            if t.startswith("--") and "=" in t:
                i += 1
            elif t in _WITH_VALUE:
                i += 2
            elif t.startswith("-") and len(t) > 1:
                i += 1
            else:
                pat = t
                break
        if pat:
            pats.append(pat)
    return pats


def searches_in(name: str, inp: dict) -> list[str]:
    if name == "Grep":
        return [inp["pattern"]] if inp.get("pattern") else []
    if name == "Bash":
        return grep_patterns(inp.get("command", "") or "")
    return []


_BASH_WRITE = re.compile(r"(\bsed\s+(-[A-Za-z]*i|--in-place)|\btee\b|\bgit\s+apply\b|\bpatch\s+-|(^|[^<>\d&])>{1,2}\s*[\w./~$\"'-]+\.\w+"
                         r"|\.write_text\(|\.write\(|open\([^)]*['\"][wax]\+?['\"]|\bcat\s*>|\bpython3?\s+-\s*<<)")


def writes_code(name: str, inp: dict) -> bool:
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return str(inp.get("file_path", "")).endswith(_CODE)
    if name == "Bash":
        c = re.sub(r">\s*/dev/null|2>&1|>&\d", "", inp.get("command", "") or "")
        return bool(_BASH_WRITE.search(c)) and not re.search(r"^\s*(pytest|python3? -m pytest)\b", c)
    return False
