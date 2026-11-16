"""An independent truth for C and C++ calls (ADR-DEVKB-008 §7, AD-10): regex over masked text, no `devkb` import.

A test scans this file's imports. It finds, for a repository, every definition and every call-site line of a name,
and decides which sites are *determinate*: the name has exactly one definition in the repository, or the site is
spelled `Class::name(`, or the callee is a `static` function of the site's own file. Caller precision and recall are
measured on determinate sites only, and the number of indeterminate sites is reported beside them, never folded in:
without type inference no truth can decide an overloaded or shared method name.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

EXTS = (".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx")
SKIP = re.compile(r"(^|/)(third_party|thirdparty|vendor|external|build|cmake-build-[^/]*)/|\.pb\.(h|cc)$|\.generated\.")
MAX_BYTES = 2 * 1024 * 1024
# The truth's own list of C library names: a repository function bearing one is never the target of a cross-file link.
LIBC = frozenset("exit abort memcpy memmove memset memcmp strlen strcpy strncpy strcmp strncmp strchr printf fprintf sprintf "
                 "snprintf puts malloc calloc realloc free fopen fclose fread fwrite atoi qsort".split())
_KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "catch", "else", "do", "case", "throw", "new", "delete",
             "defined", "alignof", "decltype", "static_assert", "assert", "operator", "typeof", "alignas"}
_STRIP = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', re.S)
_DEF = re.compile(
    r"(?m)^(?P<pre>[^\n;{}#]*?)\b(?P<qual>(?:\w+\s*::\s*)*)(?P<name>~?[A-Za-z_]\w*)\s*\((?P<args>[^;{}()]*(?:\([^()]*\)[^;{}()]*)*)\)"
    r"(?:\s*(?:const|noexcept|override|final|volatile))*\s*(?::[^;{]*)?\s*\{")
_CALL = re.compile(r"(?P<q>(?:\w+\s*::\s*)?)\b(?P<name>[A-Za-z_]\w*)\s*\(")


def _mask(text: str) -> str:
    out = _STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return re.sub(r"(?m)^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", lambda m: re.sub(r"[^\n]", " ", m.group(0)), out)


@dataclass
class Definition:
    name: str
    qualifier: str      # `Class` of `Class::name`, else ""
    file: str
    line: int
    static: bool


@dataclass
class Site:
    name: str
    file: str
    line: int
    qualifier: str
    member: bool = False                # spelled `x.name(` or `p->name(`
    target: Definition | None = None    # set when the site is determinate


@dataclass
class Truth:
    defs: dict[str, list[Definition]] = field(default_factory=dict)
    sites: dict[str, list[Site]] = field(default_factory=dict)
    files: int = 0

    def determinate(self, site: Site) -> Definition | None:
        defs = self.defs.get(site.name, [])
        if site.member and not site.qualifier:
            # a member call can only reach a method: determinate only when the one definition is `Class::name`
            return defs[0] if len(defs) == 1 and defs[0].qualifier else None
        if site.qualifier:
            hit = [d for d in defs if d.qualifier == site.qualifier]
            return hit[0] if len(hit) == 1 else None
        local = [d for d in defs if d.static and d.file == site.file]
        if local:
            return local[0] if len(local) == 1 else None
        return defs[0] if len(defs) == 1 else None


def list_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--recurse-submodules"], cwd=root, capture_output=True, text=True).stdout
    return sorted(f for f in out.splitlines() if f.lower().endswith(EXTS) and not SKIP.search(f))


def build(root: Path) -> Truth:
    t = Truth()
    texts: dict[str, str] = {}
    for rel in list_files(root):
        p = root / rel
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            texts[rel] = _mask(p.read_text(errors="replace"))
        except OSError:
            continue
    t.files = len(texts)
    def_at: set[tuple[str, int]] = set()
    for rel, text in texts.items():
        for m in _DEF.finditer(text):
            name = m.group("name")
            if name in _KEYWORDS or re.search(r"[=.]|->|\breturn\b|\belse\b", m.group("pre")):
                continue
            line = text.count("\n", 0, m.start("name")) + 1
            qual = re.sub(r"\s", "", m.group("qual")).rstrip(":").rsplit("::", 1)[-1]
            t.defs.setdefault(name, []).append(Definition(name, qual, rel, line, bool(re.search(r"\bstatic\b", m.group("pre")))))
            def_at.add((rel, m.start("name")))
    for rel, text in texts.items():
        for m in _CALL.finditer(text):
            name = m.group("name")
            if name in _KEYWORDS or name not in t.defs or (rel, m.start("name")) in def_at:
                continue
            before = text[max(0, text.rfind("\n", 0, m.start()) + 1):m.start("q") or m.start("name")]
            tail = re.split(r"[;{}]", before)[-1].rstrip()
            word = re.search(r"([A-Za-z_]\w*)$", tail)
            if word and word.group(1) not in ("return", "else", "case", "throw", "do"):
                continue            # `int name(...)`: a declaration, not a call
            member = text[:m.start()].rstrip().endswith((".", "->"))
            site = Site(name, rel, text.count("\n", 0, m.start("name")) + 1, re.sub(r"\s", "", m.group("q")).rstrip(":").rsplit("::", 1)[-1], member)
            site.target = t.determinate(site)
            t.sites.setdefault(name, []).append(site)
    return t
