#!/usr/bin/env python3
"""Independent header counts (SPEC-DKB-002 story 1.2 and 1.6): a regex count that imports nothing from devkb.

  header_counts.py REPO [--graph DIR] [--list N]

Counts, over the tracked `.h` files of REPO: how many hold a C++ construct outside every `#ifdef __cplusplus` region,
how many carry an `extern "C"` guard, and the language each would have by the ADR-DEVKB-009 order (constructs, guard,
includers, else C). With `--graph DIR` (a `.devkb` directory built by `devkb build`) it compares with devkb's File
nodes and lists every header on which they differ; exit 1 when any differs.
"""
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

CPP_EXT = (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx")
CONSTRUCT = re.compile(r"\bnamespace\s*(?:[A-Za-z_][\w:]*|\{)|\btemplate\s*<"
                       r"|\b(?:class|struct)\b[^;{}()]*\{[^{}]*?\b(?:public|private|protected)\s*:(?!:)")
STRIP = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', re.S)
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"\n]+)[>"]', re.M)


def tracked(repo: Path) -> list[str]:
    return subprocess.run(["git", "ls-files", "--recurse-submodules"], cwd=repo, capture_output=True, text=True).stdout.split("\n")


def split_regions(text: str) -> tuple[str, str]:
    """(text outside every `#ifdef __cplusplus` region, the text inside them), by a line scan with a nesting counter."""
    outside, inside, stack, continued = [], [], [], False
    for line in text.split("\n"):
        if continued:                      # the body of a multi-line directive is not code
            continued = line.rstrip().endswith("\\")
            continue
        m = re.match(r"\s*#\s*(if|ifdef|ifndef|else|elif|endif)\b(.*)", line)
        if not m and re.match(r"\s*#", line):
            continued = line.rstrip().endswith("\\")
            continue                       # `#define X extern "C"` and the like are not code either
        if m:
            continued = line.rstrip().endswith("\\")
            kw, rest = m.groups()
            if kw in ("if", "ifdef", "ifndef"):
                stack.append(kw != "ifndef" and "__cplusplus" in rest and "!" not in rest)
            elif kw in ("else", "elif") and stack:
                stack[-1] = False
            elif kw == "endif" and stack:
                stack.pop()
            continue
        (inside if any(stack) else outside).append(line)
    return "\n".join(outside), "\n".join(inside)


def facts(text: str) -> tuple[bool, bool]:
    text = re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    raw_outside, raw_inside = split_regions(text)
    guarded = bool(re.search(r'extern\s*"C"', raw_inside))
    outside = STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)) if not m.group(0).startswith('"') else '""', raw_outside)
    construct = bool(CONSTRUCT.search(outside)) or bool(re.search(r'extern\s*"C"', raw_outside))
    return construct, guarded


def main(argv: list[str]) -> int:
    repo = Path(argv[0]).resolve()
    graph = Path(argv[argv.index("--graph") + 1]) if "--graph" in argv else None
    limit = int(argv[argv.index("--list") + 1]) if "--list" in argv else 20
    files = [f for f in tracked(repo) if f.lower().endswith((".c", ".h") + CPP_EXT) and not any(s in f.split("/")[:-1] for s in ("third_party", "thirdparty", "vendor", "external", "build"))]
    headers = [f for f in files if f.lower().endswith(".h")]
    by_base: dict[str, list[str]] = {}
    for h in headers:
        by_base.setdefault(h.rsplit("/", 1)[-1], []).append(h)
    includers: dict[str, list[str]] = {}
    for f in files:
        if f.lower().endswith(".h"):
            continue
        kind = "cpp" if f.lower().endswith(CPP_EXT) else "c"
        try:
            text = (repo / f).read_text(errors="replace")
        except OSError:
            continue
        for inc in INCLUDE.findall(text):
            near = posixpath.normpath(posixpath.join(posixpath.dirname(f), inc))
            if near in headers:
                hit = [near]
            else:
                norm = posixpath.normpath(inc).lstrip("./")
                hit = [h for h in by_base.get(inc.rsplit("/", 1)[-1], []) if h == norm or h.endswith("/" + norm)]
            for h in hit:
                includers.setdefault(h, []).append(kind)
    mine: dict[str, tuple[str, bool]] = {}
    n_construct = n_guard = 0
    for h in headers:
        try:
            construct, guarded = facts((repo / h).read_text(errors="replace"))
        except OSError:
            continue
        n_construct += construct
        n_guard += guarded
        langs = includers.get(h, [])
        if construct:
            mine[h] = ("cpp", False)
        elif guarded:
            mine[h] = ("c", True)
        elif langs and all(x == "cpp" for x in langs):
            mine[h] = ("cpp", False)
        else:
            mine[h] = ("c", False)
    out = {"headers": len(headers), "with_cpp_constructs": n_construct, "guarded": n_guard,
           "cpp_by_order": sum(1 for v in mine.values() if v[0] == "cpp"), "consumed_by_cpp": sum(1 for v in mine.values() if v[1])}
    differing: list[str] = []
    if graph is not None:
        uid_file, lang, consumed = {}, {}, {}
        for line in (graph / "nodes.jsonl").read_text().splitlines():
            n = json.loads(line)
            if n["type"] == "File" and n["natural_key"] in mine:
                lang[n["natural_key"]] = n["properties"].get("language")
                consumed[n["natural_key"]] = bool(n["properties"].get("consumed_by_cpp"))
        for h, (lg, cb) in sorted(mine.items()):
            if h in lang and (lang[h] != lg or consumed[h] != cb):
                differing.append(f"{h}: independent {lg}/{cb}, devkb {lang[h]}/{consumed[h]}")
        out["devkb_cpp"] = sum(1 for v in lang.values() if v == "cpp")
        out["devkb_consumed_by_cpp"] = sum(consumed.values())
        out["differing"] = len(differing)
    print(json.dumps(out))
    for d in differing[:limit]:
        print("DIFF", d)
    return 1 if differing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
