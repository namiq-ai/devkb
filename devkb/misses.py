"""#133: the graph-miss log. When a navigation search passes through to grep because devkb could not answer (or only
partly), and grep then finds code, one line goes to `<repo>/.devkb/graph-misses.jsonl`. `devkb misses` turns the lines
into ticket drafts for a person to review and file: nothing is filed or sent anywhere. `DEVKB_MISSLOG=0` turns it off.

Standard library only: the guardrail hooks import this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

LOG_NAME = "graph-misses.jsonl"
CODE_LANG = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
             ".cs": "csharp", ".c": "c", ".h": "c/c++", ".cc": "c++", ".cpp": "c++", ".cxx": "c++", ".hpp": "c++",
             ".hh": "c++", ".hxx": "c++", ".inl": "c++", ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
             ".php": "php", ".kt": "kotlin", ".swift": "swift", ".sh": "shell"}
COMMENT = re.compile(r"^\s*(//|#(?!include|define|if|endif|else|pragma)|/\*|\*|--|<!--|\"\"\"|''')")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:::|\.)[A-Za-z_][A-Za-z0-9_]*)*")


def enabled() -> bool:
    return os.environ.get("DEVKB_MISSLOG", "1") != "0"


KEYWORDS = {"def", "class", "struct", "enum", "union", "interface", "fn", "func", "function", "void", "static", "inline",
            "virtual", "async", "return", "import", "from", "public", "private", "protected", "const", "let", "var"}
ALTERNATION = {"bre": r"\\\|", "ere": r"(?<!\\)\|", "fixed": None, "both": r"\\\||\|"}


def navigation_names(pattern: str, dialect: str = "both") -> list[str]:
    """The identifiers a search asks about: `A\\|B\\|C`, `\\bfoo\\(`, `Footer::DecodeFrom`. Empty when the pattern is
    a general regex or a phrase rather than names (then it is not a navigation search).

    Alternation is read per grep dialect (#186, #215): `\\|` in a basic regex (grep), `|` in an extended one (grep -E,
    egrep, rg, the Grep tool), neither in a fixed string (grep -F), where a `|` is just a character. A language keyword
    on its own (`^def `) is never a name (#215)."""
    p = re.sub(r"\\[bB<>]", "", pattern.strip())
    p = re.sub(r"\\s[*+]?|\\\(|\(\)|\\\)", " ", p)
    alt = ALTERNATION.get(dialect, ALTERNATION["both"])
    parts = re.split(alt, p) if alt else [p]
    names: list[str] = []
    for part in parts:
        part = part.strip().strip("()^$ ").strip()
        part = re.sub(r"^(?:async\s+def|def|class|struct|enum|union|interface|fn|func|function|void|static|inline|virtual)\s+",
                      "", part)                     # `def name`, `class Name`: the search for a definition (#131)
        part = re.sub(r"\s*\(\s*$", "", part)
        if part in KEYWORDS or not IDENT.fullmatch(part) or len(part) < 3:
            return []
        if part not in names:
            names.append(part)
    return names                                    # every name: the hook asks about at most 3 and never replaces a
                                                    # search that names more (#278)


def definition_name(pattern: str) -> str | None:
    """The one name a definition search asks for (`def NAME`, `class NAME`, `struct NAME`, `fn NAME`, `function NAME`, or
    `^\\s*NAME\\s*\\(`), else None: a search for uses, several names or a general regex is not one (SPEC-DKB-006 R1)."""
    names = navigation_names(pattern)
    if len(names) != 1 or re.search(r"\\\||\|", pattern):
        return None
    n = re.escape(names[0])
    keyword = rf"(?:^|[\^\s(]|\\[bs][*+]?)(?:async\s+def|def|class|struct|fn|function)(?:\s+|\\s[+*]?)(?:\\b)?{n}(?![\w])"
    anchored = rf"^\^(?:\\s\*|\s*){n}(?:\\s\*|\s*)\\?\("
    return names[0] if re.search(keyword, pattern) or re.match(anchored, pattern.strip()) else None


def run_definitions(repo: Path, name: str, timeout: float = 12) -> list[dict] | None:
    """The exact-name definitions of `name` from `devkb symbol NAME --source --json` (the first carries its body), or None."""
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONWARNINGS="ignore",
               DEVKB_TELEMETRY="0")
    try:
        p = subprocess.run(devkb_command(repo, "symbol", name, "--source", "--json", "--limit", "50", "--lines", "80"),
                           cwd=repo, env=env, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        r = json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if r.get("error") or r.get("n", 0) > len(r.get("matches") or []):
        return None
    return [m for m in r.get("matches") or [] if m["k"].rsplit(".", 1)[-1].split("::")[-1] == name]


def changed_since_build(repo: Path, rel: str) -> bool:
    """True when the file may differ from what the graph was built from: edited after the build, or no build time known."""
    built = 0.0
    for n in ("symbols-manifest.json", "manifest.json"):
        try:
            built = (repo / ".devkb" / n).stat().st_mtime
            break
        except OSError:
            pass
    try:
        return not built or (repo / rel).stat().st_mtime > built
    except OSError:
        return True


def verdict_of(text: str) -> tuple[str, str]:
    """(verdict, detail) from the text of `devkb pack change`: complete | incomplete | cannot-resolve | other."""
    head = "\n".join(text.splitlines()[:4])        # the verdict is in the pack's header, never in a caller's source
    if re.search(r"^The graph cannot resolve", head, re.M):
        return "cannot-resolve", next((l for l in text.splitlines() if l.startswith("The graph cannot resolve")), "")
    m = re.search(r"^\*\*Incomplete[^\n]*", text, re.M)
    if m:
        return "incomplete", re.sub(r"\*", "", m.group(0))[:300].strip()
    if re.search(r"^\*\*Complete", text, re.M):
        return "complete", ""
    return "other", ""


def devkb_command(repo: Path, *args: str) -> list[str]:
    return [sys.executable, "-P", "-m", "devkb.cli", *args, "--project", str(repo)]


def run_query(repo: Path, kind: str, name: str, timeout: float = 12) -> tuple[str, str, str] | None:
    """Run `devkb pack KIND NAME` (refactor: direct callers + definition; change: callers at any depth); (verdict, detail, answer text), or None when devkb has no graph or fails (then
    nothing is substituted and nothing is recorded)."""
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONWARNINGS="ignore",
               DEVKB_TELEMETRY="0")
    try:
        p = subprocess.run(devkb_command(repo, "pack", kind, name), cwd=repo, env=env, capture_output=True,
                           text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        verdict, detail = verdict_of(p.stdout)
        if verdict == "cannot-resolve":
            s = subprocess.run(devkb_command(repo, "symbol", name), cwd=repo, env=env, capture_output=True, text=True,
                               timeout=timeout)
            if s.returncode == 0 and re.search(r"no (?:symbol|match)|not found|0 match", s.stdout[:300], re.I):
                verdict = "no-match"
        return verdict, detail, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def graph_state(repo: Path) -> tuple[str, str]:
    """(commit the graph was built at, repository HEAD)."""
    built = ""
    for n in ("symbols-manifest.json", "manifest.json"):
        try:
            built = json.loads((repo / ".devkb" / n).read_text()).get("git_head", "") or built
        except (OSError, ValueError):
            pass
        if built:
            break
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        head = ""
    return built, head


def devkb_version() -> str:
    try:
        from importlib.metadata import version
        return version("devkb")
    except Exception:  # noqa: BLE001
        return ""


MAX_MATCHES = 50
DEF_KW = re.compile(r"\b(?:def|class|struct|enum|union|interface|fn|func|function|namespace|macro)\s+(?:[\w:]+::)?$")
CONTROL = {"if", "for", "while", "switch", "return", "catch", "sizeof", "elif", "else", "with", "assert", "not", "and",
           "or", "in", "lambda", "yield", "await", "print"}
PY_DEF = re.compile(r"^(\s*)(?:async\s+)?(?:def|class)\s+(\w+)")
C_HEAD = re.compile(r"^[A-Za-z_][\w:<>,*&\s~]*?\b([A-Za-z_~][\w:]*)\s*\([^;]*$")


def match_kind(code: str, names: list[str]) -> str:
    """definition | call | use, for one matched line of code, by the first name of the search found on it."""
    for n in names:
        short = re.split(r"::|\.", n)[-1]
        for m in re.finditer(rf"(?<![\w]){re.escape(short)}(?![\w])", code):
            before, after = code[:m.start()], code[m.end():]
            if DEF_KW.search(before.rstrip() + " ") or (re.match(r"\s*=(?!=)", after) and not before.strip()):
                return "definition"
            if re.match(r"\s*\(", after):
                head = before.strip()
                # a C/C++ definition: a type before the name, the line does not end a statement
                if head and not head.endswith((".", "->", "(", ",", "=", "return", "!", "&&", "||")) and \
                        head.split()[-1] not in CONTROL and not code.rstrip().endswith(";"):
                    return "definition"
                return "call"
            return "use"
    return "use"


def enclosing(repo: Path | None, rel: str, line: int, cache: dict) -> str:
    """The function or class whose body holds `line`, found from the file itself (Python by indentation, C-like by the
    nearest function header above), or "" at the top level or when the file cannot be read."""
    if repo is None or not line:
        return ""
    if rel not in cache:
        try:
            cache[rel] = (repo / rel).read_text(errors="replace").splitlines()
        except OSError:
            cache[rel] = []
    lines = cache[rel]
    if not lines or line > len(lines):
        return ""
    if rel.endswith(".py"):
        indent = len(lines[line - 1]) - len(lines[line - 1].lstrip())
        names = []
        for i in range(line - 2, max(-1, line - 2000), -1):
            m = PY_DEF.match(lines[i])
            if m and len(m.group(1)) < indent:
                names.append(m.group(2))
                indent = len(m.group(1))
                if indent == 0:
                    break
        return ".".join(reversed(names))
    for i in range(line - 2, max(-1, line - 400), -1):
        t = lines[i]
        if t[:1] in (" ", "\t", "}", "#", "/", "*") or not t.strip():
            continue
        m = C_HEAD.match(t)
        if m and m.group(1).split("::")[-1] not in CONTROL:
            return m.group(1)
        return ""
    return ""


NOT_ENCLOSING = {"field", "constant", "variable", "key", "import", "parameter", "enum_member"}


def graph_spans(repo: Path, rels: list[str]) -> dict[str, list[tuple[int, int, str]]]:
    """(first line, last line, qualified name) of each function, method or class the graph holds, for each file that is
    unchanged since the build (#138); files the graph does not have, or that changed, are left out. {} without a graph."""
    rels = [r for r in dict.fromkeys(rels) if not changed_since_build(repo, r)]
    if not rels:
        return {}
    try:
        from devkb.process_api import ProcessAPI  # noqa: PLC0415
        rt = ProcessAPI(str(repo), telemetry=False)._read()
    except Exception:  # noqa: BLE001  no graph, or one that cannot load: the text scan stays
        return {}
    out: dict[str, list[tuple[int, int, str]]] = {}
    for rel in rels:
        ids = rt.idx.sym_by_file.get(rel)
        if not ids:
            continue
        spans = []
        for i in ids:
            p = rt.idx.props[i]
            ls, le = p.get("line_start"), p.get("line_end")
            if ls and le and p.get("kind") not in NOT_ENCLOSING:
                spans.append((int(ls), int(le), rt.qual[i]))
        out[rel] = spans
    return out


def enclosing_from_spans(spans: list[tuple[int, int, str]], line: int) -> str:
    """The innermost definition whose lines hold `line`; "" at the top level or on the definition's own first line."""
    best = None
    for ls, le, q in spans:
        if ls < line <= le and (best is None or ls >= best[0]):
            best = (ls, le, q)
    return best[2] if best else ""


def parse_grep(text: str, files: list[str] | None = None, limit: int = 10, names: list[str] | None = None,
               repo: Path | None = None, single_file: str | None = None) -> dict:
    """What a search found, counting only code: matches in comments, docs or non-code files do not count. Each match
    is kept as `file:line` with its kind and enclosing function (up to MAX_MATCHES), so a miss can be acted on without
    running the search again (#133); the full output is not stored, only its hash. A known single file supplies the
    missing path for lines in grep's `line:text` format."""
    by_file: dict[str, int] = defaultdict(int)
    samples: list[str] = []
    matches: list[dict] = []
    cache: dict = {}
    for line in text.splitlines():
        prefix, sep, text_after_prefix = line.partition(":")
        if single_file and sep and prefix.isdecimal():
            path, number, content = single_file, prefix, text_after_prefix
        else:
            m = re.match(r"([^\s:][^:]*?):(?:(\d+):)?(.*)$", line)
            if not m:
                continue
            path, number, content = m.groups()
        if Path(path).suffix.lower() not in CODE_LANG or COMMENT.match(content):
            continue
        by_file[path] += 1
        if len(samples) < 3:
            samples.append(f"{path}:{number or ''}:{content.strip()}"[:200])
        if len(matches) < MAX_MATCHES and number:
            rel = path.removeprefix("./")
            matches.append({"at": f"{rel}:{number}", "kind": match_kind(content, names or []), "in": None})
    # the graph's own definition spans where it has the file, the text scan elsewhere (#138)
    spans = graph_spans(repo, [m["at"].rsplit(":", 1)[0] for m in matches]) if repo is not None and matches else {}
    for m in matches:
        rel, number = m["at"].rsplit(":", 1)
        m["in"] = enclosing_from_spans(spans[rel], int(number)) if rel in spans else enclosing(repo, rel, int(number), cache)
    count = sum(by_file.values())
    for f in files or []:                       # a files-only result: each code file is one match
        if Path(f).suffix.lower() in CODE_LANG and f not in by_file:
            by_file[f] += 1
            count += 1
    fl = sorted(by_file)[:limit]
    return {"count": count, "files": fl, "languages": [CODE_LANG[Path(f).suffix.lower()] for f in fl],
            "samples": samples, "matches": matches, "total": count,
            "hash": "sha1:" + hashlib.sha1(text.encode(errors="replace")).hexdigest()}


def already_logged(path: Path, session: str, repo: str, verdict: str, name: str) -> bool:
    return any((r.get("session"), r.get("repo"), r.get("verdict"), r.get("name")) == (session, repo, verdict, name)
               for r in load(path.parent.parent))


def record(pending: dict, grep: dict) -> int:
    """Append one line per name the graph missed, when grep found code. Returns the lines written."""
    if not enabled() or not grep["count"]:
        return 0
    repo = Path(pending["repo"])
    path = repo / ".devkb" / LOG_NAME
    n = 0
    for q in pending["queries"]:
        if q["verdict"] in ("complete", "other"):
            continue
        verdict = q["verdict"]                       # the cause; a graph older than HEAD is a note beside it (#133)
        stale = bool(pending.get("built") and pending.get("head") and pending["built"] != pending["head"])
        if already_logged(path, pending["session"], str(repo), verdict, q["name"]):
            continue
        line = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": pending["session"], "repo": str(repo),
                "built_at": pending.get("built", ""), "head": pending.get("head", ""),
                "devkb_version": pending.get("version", ""), "tool": pending["tool"], "pattern": pending["pattern"],
                "names": pending["names"], "name": q["name"], "devkb_query": q["query"], "verdict": verdict,
                "devkb_detail": q["detail"], "stale": stale, "grep": grep,
                "kind": "graph-incomplete" if verdict == "incomplete" else "graph-missed"}
        try:
            with open(path, "a") as fh:
                fh.write(json.dumps(line) + "\n")
            n += 1
        except OSError:
            return n
    return n


# ── devkb misses ──────────────────────────────────────────────────────────────
def load(repo: Path) -> list[dict]:
    out = []
    try:
        for l in (repo / ".devkb" / LOG_NAME).read_text().splitlines():
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def groups(rows: list[dict]) -> list[dict]:
    g: dict[tuple, dict] = {}
    for r in rows:
        k = (r["verdict"], r.get("name") or (r.get("names") or [""])[0])
        e = g.setdefault(k, {"verdict": k[0], "name": k[1], "kind": r["kind"], "count": 0, "first": r["t"], "last": r["t"],
                             "rows": []})
        e["count"] += 1
        e["first"], e["last"] = min(e["first"], r["t"]), max(e["last"], r["t"])
        e["rows"].append(r)
    return sorted(g.values(), key=lambda e: (-e["count"], e["verdict"], e["name"]))


def grep_command(r: dict) -> str:
    return f"grep -rn {shlex.quote(r.get('name') or r['pattern'])} ."


def draft(e: dict, repo: Path) -> str:
    r = e["rows"][-1]
    g = r["grep"]
    sev = "medium" if e["verdict"] != "incomplete" else "low"
    reproduce = [f"1. `{r['devkb_query']}`", f"2. `{grep_command(r)}` (in `{r['repo']}`)"]
    sample = "\n".join(f"    {s}" for s in g["samples"]) or "    (files only)"
    shown = g.get("matches", [])[:15]
    where = "\n".join(f"    - `{x['at']}` {x['kind']}" + (f" in `{x['in']}`" if x.get("in") else "") for x in shown)
    if g.get("total", 0) > len(shown):
        where += f"\n    - ... {g['total'] - len(shown)} more (the reproduce grep lists them)"
    what = ("devkb answered Incomplete" if e["verdict"] == "incomplete" else
            "devkb has no symbol for the name" if e["verdict"] == "no-match" else "devkb could not resolve the name")
    return "\n".join([
        f"### Draft ticket: graph {e['verdict']} for `{e['name']}`", "",
        f"**Severity:** {sev}.", "",
        f"**Who is affected and why it matters:** agents using devkb in `{r['repo']}`: the search passed through to grep "
        f"({e['count']} time(s), {e['first']} to {e['last']}), so the graph's answer did not save them the search.", "",
        "**Reproduce:**", *reproduce, "",
        f"**Actual:** {what}" + (f": {r['devkb_detail']}" if r["devkb_detail"] else "") + f". grep found {g['count']} code "
        f"match(es) in {len(g['files'])} file(s) ({', '.join(sorted(set(g['languages'])))}):", sample, "",
        "**Where grep found it** (what the graph should have had):", where or "    (no line numbers)", "",
        *(["**Note:** the graph was older than HEAD when this was recorded; rebuild and re-run the reproduce command "
           "first, but the verdict above is the cause to fix."] if r.get("stale") else []), "",
        "**Expected:** the graph resolves the name and answers Complete, or the pack returns the text matches itself.", "",
        "**Where to start:** `devkb/packs.py` `_resolve` / `_by_symbol_rules` for cannot-resolve and no-match; "
        "`Packer._coverage_core` and the call resolver for Incomplete; the language extractor for a definition grep "
        "found but the graph lacks. "
        f"Graph built at `{r['built_at'][:10]}`, repository HEAD `{r['head'][:10]}`, devkb {r['devkb_version']}.", "",
        "**Done when:** the reproduce command (1) answers resolved and Complete for this name, and agrees with grep (2).", ""])


def render(repo: Path) -> str:
    rows = load(repo)
    if not rows:
        return f"devkb misses: no graph misses logged in {repo / '.devkb' / LOG_NAME}."
    gs = groups(rows)
    out = [f"{len(rows)} graph miss(es) in {len(gs)} group(s). Review each, then file what is real; nothing is filed "
           "or sent automatically.", "", f"{'verdict':<15} {'name':<32} {'count':>5}  {'first seen':<19}  last seen"]
    for e in gs:
        out.append(f"{e['verdict']:<15} {e['name'][:32]:<32} {e['count']:>5}  {e['first']:<19}  {e['last']}")
    out.append("")
    for e in gs:
        out.append(draft(e, repo))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="devkb misses", description="graph misses grep found, as ticket drafts")
    ap.add_argument("--project", default=".")
    a = ap.parse_args(argv)
    repo = Path(a.project).resolve()
    print(render(repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
