"""C and C++ extraction (ADR-DEVKB-008, DKB-002/003/004/005): text in, records out.

A sibling of `ts_symbols.py`: standard library only, regex and brace matching over source text, no compiler, no
preprocessor, no type inference. The module is pure: it reads no graph, holds no mutable module state and imports
nothing from `devkb`. Resolution of calls is `cpp_resolve`; writing graph rows is `cpp_graph`.

What it produces for one file (`extract_file`):
  * definitions (`Def`): functions, methods, classes/structs/unions, enums, and brace-bodied macro invocations
    (`TEST(a, b) { ... }`, kept as `kind="macro"` for `cpp_graph` to turn into test symbols);
  * call sites, each with the form that decides how it may be resolved (bare, qualified, member + receiver);
  * class records (bases, member declarations, declared methods) for receiver typing;
  * indirect references (a function's name used without a call) and error sites (`throw`, `assert`, log macros).

Masking comes first: comments, string and character literals and `#if 0` regions are blanked (same length, same
newlines) so no later regex sees them; preprocessor directives are recorded (`#define` bodies, `#include`s) and
blanked too. Nothing is expanded: that is a stated limit (`CXX_LIMITS_TEXT`).
"""
from __future__ import annotations

import re
import subprocess
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

CXX_EXTS = (".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx")
MAX_FILE_BYTES = 2 * 1024 * 1024

# The sole source of the limit statement (ADR-DEVKB-008 §4, AD-7). Read by packs.py and by the README test.
CXX_LIMITS_TEXT = (
    "C/C++ limits: no preprocessor expansion (macro-generated definitions and calls are not seen), "
    "no overload resolution (overloads share one node), no type inference (a call through `auto`, an alias or an "
    "untyped receiver is not attributed); vendored and generated paths are not read; error-return codes "
    "(`return -EINVAL`, `return Status::Corruption(...)`) are not attributed; pybind11 class bindings (`py::class_`) are not read."
)

# The C profile's limits (ADR-DEVKB-009 §2): what a C pack cannot see. No overloads or receivers here: C has none.
C_LIMITS_TEXT = (
    "C limits: no preprocessor expansion (macro-generated definitions and calls are not seen); a call through a "
    "function pointer or an ops table is not followed (the table entry is an indirect reference); a `static` function "
    "is resolved inside its own file only; vendored and generated paths are not read; error-return codes "
    "(`return -EINVAL`) are not attributed."
)

_SKIP_SEGMENTS = {"third_party", "thirdparty", "vendor", "external", "build"}
_SKIP_SUFFIXES = (".pb.h", ".pb.cc")


def is_cxx_path(path: str) -> bool:
    return path.lower().endswith(CXX_EXTS)


def is_skipped_path(path: str) -> bool:
    """Vendored, generated or build-output paths: never read (ADR §2)."""
    parts = path.split("/")
    for seg in parts[:-1]:
        if seg in _SKIP_SEGMENTS or seg.startswith("cmake-build-"):
            return True
    name = parts[-1]
    return name.endswith(_SKIP_SUFFIXES) or ".generated." in name


def list_files(repo_root: Path) -> list[str]:
    """Tracked C/C++ files, sorted, vendored/generated paths removed. `git ls-files`, as the other extractors do."""
    proc = subprocess.run(
        ["git", "ls-files", "--recurse-submodules", "--", *[f"*{e}" for e in CXX_EXTS]],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    return sorted({f for f in proc.stdout.splitlines() if f.strip() and is_cxx_path(f) and not is_skipped_path(f)})


# ── masking ────────────────────────────────────────────────────────────────────
_LEX = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|(?<=R)\"(?P<delim>[^()\s\\]{0,16})\((?P<raw>.*?)\)(?P=delim)\""
    r"|\"(?P<str>(?:[^\"\\\n]|\\.)*)\""
    r"|'(?:[^'\\\n]|\\.)*'",
    re.S,
)
_DIRECTIVE = re.compile(r"^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", re.M)
_DEFINE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)(\()?(.*)", re.S)
_INCLUDE = re.compile(r"#\s*include\s*(?:<([^>\n]*)>|(\"))")
_BLANK = re.compile(r"[^\n]")


def _blank(s: str) -> str:
    return " " * len(s) if "\n" not in s else "\n".join(" " * len(x) for x in s.split("\n"))


@dataclass
class Masked:
    code: str                      # comments, literals, directives, `#if 0` blanked; same length and newlines as the source
    literals: dict[int, str]       # offset of a string literal's opening quote -> its raw text
    defines: list[tuple[str, str, int]]   # (name, body, 1-based line)
    includes: list[str]
    line_starts: list[int] = field(default_factory=list)
    guards: list[tuple[int, int]] = field(default_factory=list)   # spans inside `#ifdef __cplusplus` (SPEC-DKB-002 R2)
    conds: list[tuple[int, str]] = field(default_factory=list)    # (line, text) of `#if/#ifdef/#ifndef/#elif` (SPEC-DKB-002 R15)

    def line(self, offset: int) -> int:
        return bisect_right(self.line_starts, offset)


def mask_source(text: str) -> Masked:
    literals: dict[int, str] = {}
    parts: list[str] = []
    pos = 0
    for m in _LEX.finditer(text):
        parts.append(text[pos:m.start()])
        if m.group("raw") is not None:
            literals[m.start()] = m.group("raw")
            parts.append('"' + _blank(m.group(0))[1:-1] + '"')
        elif m.group("str") is not None:
            literals[m.start()] = m.group("str")
            parts.append('"' + " " * (m.end() - m.start() - 2) + '"')
        else:
            parts.append(_blank(m.group(0)) if m.group(0)[0] != "'" else "'" + " " * (m.end() - m.start() - 2) + "'")
        pos = m.end()
    parts.append(text[pos:])
    code = "".join(parts)
    # `#include "x"` keeps its literal under the quote offset; angle includes are plain text.
    includes: list[str] = []
    defines: list[tuple[str, str, int]] = []
    spans: list[tuple[int, int]] = []
    stack: list[bool] = []
    gstack: list[int | None] = []      # per open conditional: start of a positive `__cplusplus` region, else None
    guards: list[tuple[int, int]] = []
    conds: list[tuple[int, str]] = []
    skipping: int | None = None
    skip_from = 0
    line_starts = [0] + [m.end() for m in re.finditer("\n", code)]
    for d in _DIRECTIVE.finditer(code):
        body = d.group(0)
        kw = re.match(r"\s*#\s*(\w+)", body)
        word = kw.group(1) if kw else ""
        if word in ("if", "ifdef", "ifndef"):
            stack.append(True)
            positive = word != "ifndef" and re.search(r"\b__cplusplus\b", body) and not re.search(r"!\s*(?:defined\b|\()?\s*\(?\s*__cplusplus", body)
            gstack.append(d.end() if positive else None)
        if word in ("if", "ifdef", "ifndef", "elif") and skipping is None:
            conds.append((bisect_right(line_starts, d.start()), body))
        if word in ("if", "ifdef", "ifndef"):
            if skipping is None and word == "if" and re.match(r"\s*#\s*if\s*\(?\s*0\s*\)?\s*$", body.split("\\\n")[0]):
                skipping, skip_from = len(stack), d.end()
        elif word in ("else", "elif", "endif"):
            if gstack and gstack[-1] is not None:
                guards.append((gstack[-1], d.start()))
                gstack[-1] = None
            if word == "endif" and gstack:
                gstack.pop()
            if skipping == len(stack):
                spans.append((skip_from, d.start()))
                skipping = None
            if word == "endif" and stack:
                stack.pop()
        if skipping is not None and skip_from <= d.start() and word not in ("else", "elif", "endif"):
            spans.append((d.start(), d.end()))
            continue
        if word == "include":
            im = _INCLUDE.match(body)
            if im:
                includes.append(im.group(1) if im.group(1) is not None else literals.get(d.start() + body.index('"'), ""))
        elif word == "define":
            dm = _DEFINE.match(body.replace("\\\n", " \n"))
            if dm:
                defines.append((dm.group(1), dm.group(3), bisect_right(line_starts, d.start())))
        spans.append((d.start(), d.end()))
    if skipping is not None:
        spans.append((skip_from, len(code)))
    if spans:
        spans.sort()
        out: list[str] = []
        pos = 0
        for a, b in spans:
            if b <= pos:
                continue
            a = max(a, pos)
            out.append(code[pos:a])
            out.append(_blank(code[a:b]))
            pos = b
        out.append(code[pos:])
        code = "".join(out)
    code = _blank_dialect(code)
    return Masked(code, literals, defines, includes, line_starts, guards, conds)


# ── dialect keywords (ADR-DEVKB-009 §2, SPEC-DKB-002 R6): the one closed table, read without any compiler ─────────
# A keyword is added only with a line of tests/fixtures/profiles/dialect that uses it (a test fails for an unused entry).
DIALECT_KEYWORDS = ("__interrupt", "__irq", "__ramfunc", "__root", "__weak", "__packed")    # plain words: blanked
DIALECT_PAREN = ("__attribute__", "__asm__", "__svc")                                        # word + (...): blanked whole
_DIALECT_WORD = re.compile(r"\b(?:" + "|".join(DIALECT_KEYWORDS) + r")\b")
_DIALECT_PAREN = re.compile(r"\b(?:" + "|".join(DIALECT_PAREN) + r")\b(?:\s*(?:volatile|__volatile__)\b)?\s*(?=\()")


def _blank_dialect(code: str) -> str:
    """Blank dialect keywords (same length, same newlines) so they are read neither as a call nor as part of a definition."""
    if "__" not in code:
        return code
    code = _DIALECT_WORD.sub(lambda m: " " * len(m.group(0)), code)
    out: list[str] = []
    pos = 0
    for m in _DIALECT_PAREN.finditer(code):
        if m.start() < pos:
            continue
        close = _match_close(code, m.end(), "(", ")")
        if close is None:
            continue
        out.append(code[pos:m.start()])
        out.append(_blank(code[m.start():close + 1]))
        pos = close + 1
    if not out:
        return code
    out.append(code[pos:])
    return "".join(out)


# ── language of a file (ADR-DEVKB-009 §2) ──────────────────────────────────────
_CPP_CONSTRUCT = re.compile(
    r"\bnamespace\s*(?:[A-Za-z_][\w:]*|\{)|\btemplate\s*<"
    r"|\b(?:class|struct)\b[^;{}()]*\{[^{}]*?\b(?:public|private|protected)\s*:(?!:)"
)
_EXTERN_STR = re.compile(r"\bextern\s*\"")
CPP_EXTS = (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx")


def header_facts(m: Masked) -> tuple[bool, bool]:
    """(a C++ construct outside every `#ifdef __cplusplus` region, an `extern "C"` inside one): the two facts a `.h` is read by."""
    code = m.code
    guarded = False
    for a, b in m.guards:
        for em in _EXTERN_STR.finditer(code, a, b):
            if m.literals.get(em.end() - 1) == "C":
                guarded = True
    outside = code
    for a, b in m.guards:
        outside = outside[:a] + _blank(outside[a:b]) + outside[b:]
    construct = bool(_CPP_CONSTRUCT.search(outside))
    if not construct:
        construct = any(m.literals.get(em.end() - 1) == "C" for em in _EXTERN_STR.finditer(outside))
    return construct, guarded


_CALL_NAME = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def c_declared_names(m: Masked) -> set[str]:
    """Names written before a `(` inside an `extern "C" { ... }` block of a guarded header: functions declared with C linkage.

    A C++ file that includes the header and defines one of them without writing `extern "C"` again still defines a
    function with C linkage (the first declaration decides); the scanner reads this to label such a definition."""
    names: set[str] = set()
    for a, b in m.guards:
        for em in _EXTERN_STR.finditer(m.code, a, b):
            if m.literals.get(em.end() - 1) != "C":
                continue
            after = em.end() + len(m.literals[em.end() - 1]) + 1        # past the closing quote of "C"
            brace = re.compile(r"\s*\{").match(m.code, after)
            end = _match_close(m.code, brace.end() - 1, "{", "}") if brace else None
            names.update(_CALL_NAME.findall(m.code, after, end if end is not None else b))
    return names


def header_language(facts: tuple[bool, bool], includer_languages: list[str]) -> tuple[str, bool]:
    """`.h` rule of ADR-DEVKB-009 §2: (language, consumed_by_cpp). Constructs first, then the guard, then the includers, else C."""
    construct, guarded = facts
    if construct:
        return "cpp", False
    if guarded:
        return "c", True
    if includer_languages and all(lang == "cpp" for lang in includer_languages):
        return "cpp", False
    return "c", False


def file_language(path: str, m: Masked | None = None, includer_languages: list[str] | None = None) -> tuple[str, bool]:
    """(language, consumed_by_cpp) of one path; a `.h` needs its masked text, and its includers when known."""
    low = path.lower()
    if low.endswith(".c"):
        return "c", False
    if low.endswith(".h"):
        return header_language(header_facts(m) if m is not None else (False, False), includer_languages or [])
    return "cpp", False


def looks_cpp(code: str, path: str) -> bool:
    """Kept for callers of the old name: the language of `path` read alone, without includers."""
    return file_language(path, mask_source(code) if path.lower().endswith(".h") else None)[0] == "cpp"


# ── records ────────────────────────────────────────────────────────────────────
@dataclass
class Def:
    qn: str
    short: str
    kind: str                       # function | method | class | enum | macro
    namespace: str
    line: int
    line_end: int
    is_public: bool = True
    virtual: bool = False
    class_chain: tuple[str, ...] = ()
    locals: dict[str, set] | None = None   # name -> {(type, ptr)} or {None} when not provable; parsed on first need
    params: str = ""
    spans: list = field(default_factory=list)   # (lo, hi) offsets scanned for calls and errors
    macro_name: str = ""
    macro_args: str = ""            # masked argument text
    macro_args_offset: int = 0
    macro_line: int = 0
    body: tuple[int, int] = (0, 0)  # offsets inside the masked code
    index: int = -1
    linkage: str = ""               # functions and methods: internal | c | cpp (ADR-DEVKB-009 §2)


@dataclass
class ClassRec:
    qn: str
    kind: str
    line: int
    bases: list[str] = field(default_factory=list)
    members: dict[str, tuple[str, str] | None] = field(default_factory=dict)
    methods: dict[str, bool] = field(default_factory=dict)   # declared or defined method name -> virtual?


@dataclass
class Call:
    caller: int          # index into FileRecords.defs
    name: str
    form: str            # bare | qualified | member
    qualifier: str       # `A::B` for qualified, else ""
    recv: str | None     # receiver identifier for member calls (`this` included), None when not a plain identifier
    recv_local: object   # (type, ptr) when the receiver is a provable local/param, False when local but unprovable, None when not local
    line: int


@dataclass
class ErrorSite:
    caller: int
    kind: str            # raises | logs | unattributed
    label: str
    message: str | None
    source: str          # cpp-throw | cpp-assert | cpp-log-macro
    line: int


@dataclass
class FileRecords:
    path: str
    cpp: bool
    defs: list[Def]
    classes: list[ClassRec]
    calls: list[Call]
    errors: list[ErrorSite]
    indirect: list[tuple[str, int, int]]      # (name, line, enclosing def index or -1)
    define_names: set[str]
    namespaces: set[str]
    includes: list[str]
    masked: Masked | None = None
    scanner: object = None
    consumed_by_cpp: bool = False        # a C header with an `extern "C"` guard (ADR-DEVKB-009 §2)

    @property
    def language(self) -> str:
        return "cpp" if self.cpp else "c"


# ── scanning helpers ───────────────────────────────────────────────────────────
_IDENT = r"[A-Za-z_]\w*"
_TARGS = r"<(?:[^<>;{}()]|<(?:[^<>;{}()]|<[^<>;{}()]*>)*>)*>"
_NOT_FUNC = {
    "if", "while", "for", "switch", "return", "sizeof", "alignas", "alignof", "decltype", "noexcept", "throw", "catch",
    "__attribute__", "__declspec", "static_assert", "typeof", "__typeof__", "defined", "else", "do", "case", "new",
    "delete", "typeid", "co_return", "co_await", "co_yield", "static_cast", "dynamic_cast", "reinterpret_cast",
    "const_cast", "assert", "requires", "operator",
}
_TYPE_KEYWORDS = {
    "return", "delete", "else", "case", "throw", "goto", "new", "sizeof", "typedef", "using", "namespace", "do", "if",
    "while", "for", "switch", "co_return", "co_yield", "co_await", "public", "private", "protected", "default",
    "break", "continue", "template", "operator", "this", "true", "false", "nullptr",
}
_CALL_AFTER = {"return", "else", "case", "throw", "co_return", "co_await", "co_yield", "do", "delete"}
_CAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")

_CAND = re.compile(
    r"(?P<name>(?P<qual>(?:::\s*)?(?:" + _IDENT + r"\s*(?:" + _TARGS + r")?\s*::\s*)*)"
    r"(?P<last>operator\s*(?:\(\s*\)|\[\s*\]|(?:new|delete)(?:\s*\[\s*\])?|->\*?|[-+*/%^&|~!=<>]+|,|"
    + _IDENT + r"(?:\s*[*&]+)?)|~\s*" + _IDENT + r"|" + _IDENT + r"))"
    r"(?P<targs>\s*" + _TARGS + r")?\s*\("
)
_ATTR = re.compile(r"\[\[[^\]]*\]\]|__attribute__\s*\(\(.*?\)\)|__declspec\s*\([^)]*\)|\balignas\s*\([^)]*\)", re.S)
_ACCESS = re.compile(r"(?:\b(public|private|protected)\b\s*:(?!:)\s*)+")
_EXTERN_C = re.compile(r"^\s*extern\s*\"[^\"]*\"\s*$")
_CLASS_HEAD = re.compile(r"^\s*(?:(?:typedef|friend|static|extern|const|volatile|inline|[A-Z][A-Z0-9_]*)\s+)*(class|struct|union)\b(.*)$", re.S)
_ENUM_HEAD = re.compile(r"^\s*(?:typedef\s+)?(?:[A-Z][A-Z0-9_]*\s+)*enum\b\s*(?:class\b|struct\b)?\s*(.*)$", re.S)
_NS_HEAD = re.compile(r"^\s*(?:inline\s+)?namespace\b(.*)$", re.S)
_LITERAL_CHAIN = re.compile(r"^(?:\s*(?:u8|[uUL])?\"[^\"]*\"\s*)+$")


def _set_access(text: str, scope: "_Scope") -> None:
    last = None
    for m in re.finditer(r"\b(public|private|protected)\b\s*:(?!:)", text):
        last = m.group(1)
    if last:
        scope.access = last


def _blank_span(s: str, a: int, b: int) -> str:
    return s[:a] + _blank(s[a:b]) + s[b:]


def _strip_decor(h: str) -> str:
    """Attributes, access specifiers and a leading `template<...>` blanked, offsets preserved."""
    for m in list(_ATTR.finditer(h)):
        h = _blank_span(h, m.start(), m.end())
    for m in list(_ACCESS.finditer(h)):
        h = _blank_span(h, m.start(), m.end())
    while True:
        m = re.match(r"\s*template\s*<", h)
        if not m:
            break
        depth, k = 1, m.end()
        while k < len(h) and depth:
            depth += {"<": 1, ">": -1}.get(h[k], 0)
            k += 1
        h = _blank_span(h, 0, k)
    return h


def _match_close(code: str, open_i: int, o: str, c: str, limit: int | None = None) -> int | None:
    """Offset of the bracket closing the one at `open_i`, or None."""
    depth = 0
    pat = _BR[o]
    end = len(code) if limit is None else limit
    for m in pat.finditer(code, open_i, end):
        depth += 1 if m.group() == o else -1
        if depth == 0:
            return m.start()
    return None


_BR = {"{": re.compile(r"[{}]"), "(": re.compile(r"[()]"), "[": re.compile(r"[\[\]]")}


def _split_top(s: str, sep: str = ",") -> list[str]:
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == sep and depth <= 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


_VAR_TYPE = (r"(?P<type>(?:::)?" + _IDENT + r"(?:::" + _IDENT + r")*)(?:\s+const)?(?P<ptr>(?:\s*(?:const\b\s*)?[*&]+(?:\s*const\b)?)*)")
_PARAM = re.compile(
    r"^\s*(?:(?:const|volatile|struct|class|union|enum|unsigned|signed|register|typename)\s+)*" + _VAR_TYPE
    + r"\s*(?P<name>" + _IDENT + r")?\s*(?:\[[^\]]*\])?\s*$", re.S)
_LOCAL = re.compile(
    r"(?:^|[;{}(])\s*(?:(?:const|static|volatile|register|struct|class|union|enum|typename|extern|mutable|constexpr|"
    r"thread_local|unsigned|signed)\s+)*" + _VAR_TYPE + r"\s*(?P<name>" + _IDENT + r")\s*(?=[=;,\[({)])")
_TEMPL_LOCAL = re.compile(r">\s*[*&]*\s*(" + _IDENT + r")\s*(?=[=;({,])")


def _ptr_norm(ptr: str) -> str:
    return re.sub(r"\s|const", "", ptr)


def _decl_type(m: re.Match) -> tuple[str, str] | None:
    t = m.group("type").lstrip(":")
    if t in _TYPE_KEYWORDS or t in ("auto", "void", "int", "char", "long", "short", "float", "double", "bool", "size_t"):
        return None
    p = _ptr_norm(m.group("ptr"))
    return (t, p) if p in ("", "*", "&", "&&") else None


def _parse_params(text: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for p in _split_top(text):
        p = p.split("=", 1)[0]
        if not p.strip() or p.strip() == "void":
            continue
        m = _PARAM.match(p)
        if m and m.group("name"):
            out.setdefault(m.group("name"), set()).add(_decl_type(m))
        else:
            ids = re.findall(_IDENT, re.sub(_TARGS, " ", p))
            if ids and not (m and not m.group("name")):
                out.setdefault(ids[-1], set()).add(None)
    return out


def _parse_locals(body: str, into: dict[str, set]) -> None:
    for m in _LOCAL.finditer(body):
        if m.group("type") in _TYPE_KEYWORDS:
            continue
        into.setdefault(m.group("name"), set()).add(_decl_type(m))
    for m in _TEMPL_LOCAL.finditer(body):
        into.setdefault(m.group(1), set()).add(None)


def _norm_name(text: str) -> str:
    if text.isidentifier():
        return text
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"\s*(::|~)\s*", r"\1", text)
    if text.endswith(" "):
        text = text.strip()
    return re.sub(r"operator\s*([^\w\s])", r"operator\1", re.sub(r"operator\s*(\(\s*\)|\[\s*\])", lambda m: "operator" + re.sub(r"\s", "", m.group(1)), text))


# ── the file scanner ───────────────────────────────────────────────────────────
class _Scope:
    __slots__ = ("ns", "anon", "classes", "access", "rec", "ext_c")

    def __init__(self, ns=(), anon=False, classes=(), access="public", rec=None, ext_c=False):
        self.ns, self.anon, self.classes, self.access, self.rec, self.ext_c = ns, anon, classes, access, rec, ext_c


class _Scanner:
    def __init__(self, path: str, masked: Masked, cpp: bool, ns_seen: set[str]):
        self.path, self.m, self.code, self.cpp, self.ns_seen = path, masked, masked.code, cpp, ns_seen
        self.defs: list[Def] = []
        self.classes: list[ClassRec] = []
        self.calls: list[Call] = []
        self.errors: list[ErrorSite] = []

    # statement walker -------------------------------------------------------
    def walk(self, lo: int, hi: int, scope: _Scope) -> None:
        code = self.code
        i = start = lo
        pat = re.compile(r"[;{}(]")
        while i < hi:
            m = pat.search(code, i, hi)
            if not m:
                break
            c, k = m.group(), m.start()
            if c == "(":
                close = _match_close(code, k, "(", ")", hi)
                i = (close + 1) if close is not None else k + 1
            elif c == ";":
                self.decl(start, k, scope)
                i = start = k + 1
            elif c == "}":
                i = start = k + 1
            else:  # "{"
                close = _match_close(code, k, "{", "}", hi)
                if close is None:
                    close = hi
                end = self.brace(start, k, close, scope)
                i = start = close + 1 if end is None else end
        # trailing statement without terminator: ignore

    def brace(self, start: int, k: int, close: int, scope: _Scope) -> int | None:
        code = self.code
        _set_access(code[start:k], scope)
        h = _strip_decor(code[start:k])
        if self.cpp:
            m = _NS_HEAD.match(h)
            if m:
                rest = re.sub(r"\([^)]*\)", " ", m.group(1))
                nm = re.match(r"\s*(" + _IDENT + r"(?:\s*::\s*" + _IDENT + r")*)", rest)
                if nm:
                    chain = tuple(re.sub(r"\s", "", nm.group(1)).split("::"))
                    self.walk(k + 1, close, _Scope(scope.ns + chain, scope.anon, scope.classes, "public", None, scope.ext_c))
                else:
                    self.walk(k + 1, close, _Scope(scope.ns, True, scope.classes, "public", None, scope.ext_c))
                return None
            if _EXTERN_C.match(h):
                self.walk(k + 1, close, _Scope(scope.ns, scope.anon, scope.classes, scope.access, scope.rec, True))
                return None
        elif _EXTERN_C.match(h):
            self.walk(k + 1, close, _Scope(scope.ns, scope.anon, scope.classes, scope.access, scope.rec, True))
            return None
        hs = re.sub(r"^\s*extern\s*\"[^\"]*\"", lambda mm: " " * len(mm.group(0)), h)
        em = _ENUM_HEAD.match(hs) if "enum" in hs else None
        if em and "(" not in hs and "=" not in hs.replace("==", ""):
            nm = re.match(r"\s*(?:[A-Z][A-Z0-9_]*\s+)*(" + _IDENT + r")\b(?!\s*\()", em.group(1))
            name = nm.group(1) if nm else None
            if name is None and re.match(r"^\s*typedef\b", hs):
                name = self.typedef_name(close)
            if name and name not in ("class", "struct"):
                pos = start + hs.find(name, hs.find("enum"))
                self.add_def(Def(name if not scope.classes else ".".join(scope.classes + (name,)), name, "enum",
                                 "::".join(scope.ns), self.m.line(pos), self.m.line(close),
                                 is_public=not scope.anon and scope.access == "public", class_chain=scope.classes))
            return None
        cm = _CLASS_HEAD.match(hs) if ("class" in hs or "struct" in hs or "union" in hs) else None
        if cm and (self.cpp or cm.group(1) != "class"):
            rest = cm.group(2)
            parts = re.split(r"(?<!:):(?!:)", rest, maxsplit=1)
            head, bases_text = parts[0], (parts[1] if len(parts) > 1 else "")
            plain = re.sub(_TARGS, " ", head)
            plain = re.sub(r"\b[A-Z][A-Z0-9_]*\s*\([^)]*\)", " ", plain)
            if not re.search(r"[()=*&]", plain):
                ids = [t for t in re.findall(_IDENT, plain) if t != "final"]
                name = ids[-1] if ids else None
                if name is None and re.match(r"^\s*typedef\b", hs):
                    name = self.typedef_name(close)
                if name:
                    kw = cm.group(1)
                    pos = start + hs.rfind(name, 0, len(hs) - len(bases_text)) if name in head else start + hs.find(name)
                    chain = scope.classes + (name,)
                    qn = ".".join(chain)
                    rec = ClassRec(qn, kw, self.m.line(pos))
                    for b in _split_top(re.sub(r"\b(?:public|private|protected|virtual)\b", " ", re.sub(_TARGS, "", bases_text))):
                        b = re.sub(r"\s", "", b).lstrip(":")
                        if b and re.match(r"^[\w:]+$", b):
                            rec.bases.append(b)
                    self.classes.append(rec)
                    self.add_def(Def(qn, name, "class", "::".join(scope.ns), rec.line, self.m.line(close),
                                     is_public=not scope.anon and scope.access == "public", class_chain=scope.classes))
                    self.walk(k + 1, close, _Scope(scope.ns, scope.anon, chain, "public" if kw != "class" else "private", rec))
                    return None
        # a function or macro-bodied definition
        fn = self.function(start, k, close, h, scope)
        if fn:
            return None
        return None

    def typedef_name(self, close: int) -> str | None:
        m = re.match(r"\s*(?:\*\s*)?(" + _IDENT + r")\s*[;,\[]", self.code[close + 1:close + 200])
        return m.group(1) if m else None

    def add_def(self, d: Def) -> Def:
        d.index = len(self.defs)
        self.defs.append(d)
        return d

    # a declaration (no body) -------------------------------------------------
    def decl(self, start: int, end: int, scope: _Scope) -> None:
        rec = scope.rec
        if rec is None:
            return
        h = _strip_decor(self.code[start:end])
        _set_access(self.code[start:end], scope)
        if re.match(r"\s*(?:typedef|using|friend|static_assert|template\s*<[^>]*>\s*(?:class|struct)|enum|class|struct|union)\b", h):
            return
        if "(" in h:
            mm = next((c for c in _CAND.finditer(h) if _norm_name(c.group("last")) not in _NOT_FUNC), None)
            if mm is not None and not mm.group("qual").strip():
                short = _norm_name(mm.group("last"))
                if short not in _NOT_FUNC:
                    rec.methods[short] = rec.methods.get(short, False) or bool(re.search(r"\bvirtual\b|\boverride\b", h))
            return
        fm = re.match(r"^\s*(?:(?:mutable|static|const|volatile|constexpr|inline|thread_local|struct|class|enum)\s+)*" + _VAR_TYPE
                      + r"\s*(?P<name>" + _IDENT + r")\s*(?:\[[^\]]*\])?\s*(?:=.*|\{.*|:\s*\d+)?\s*$", h, re.S)
        if fm:
            rec.members[fm.group("name")] = _decl_type(fm)
        else:
            ids = re.findall(_IDENT, re.sub(_TARGS, " ", h.split("=", 1)[0]))
            if ids:
                rec.members.setdefault(ids[-1], None)

    # a function definition ---------------------------------------------------
    def function(self, start: int, k: int, close: int, h: str, scope: _Scope) -> bool:
        hs = re.sub(r"^\s*extern\s*\"[^\"]*\"", lambda mm: " " * len(mm.group(0)), h)
        pos = 0
        pick = None
        while True:
            m = _CAND.search(hs, pos)
            if not m:
                return False
            open_i = m.end() - 1
            cl = _match_close(hs, open_i, "(", ")")
            if cl is None:
                return False
            last = _norm_name(m.group("last"))
            if last in _NOT_FUNC:
                pos = cl + 1
                continue
            qual_empty = not m.group("qual").strip()
            tail = hs[cl + 1:]
            if qual_empty and _CAPS.match(last) and re.match(r"\s*[A-Za-z_*&]", tail) and not re.match(r"\s*(?:const|noexcept|override|final|volatile|try)\b", tail):
                pos = cl + 1   # an all-caps wrapper before the return type (`CJSON_PUBLIC(cJSON *) cJSON_Parse(...)`)
                continue
            pick = (m, open_i, cl)
            break
        m, open_i, cl = pick
        prefix = hs[:m.start()]
        if re.search(r"[=.]|->|[;]", re.sub(r"==|<=|>=", "", prefix)) and "operator" not in prefix:
            return False
        if re.search(r"\b(?:return|else|typedef|using|new|delete)\b", prefix):
            return False
        qual = re.sub(r"\s|<[^>]*>", "", m.group("qual")).lstrip(":")
        qparts = [p for p in qual.split("::") if p]
        short = _norm_name(m.group("last"))
        has_type = bool(re.search(r"[A-Za-z_]", prefix))
        in_class = bool(scope.classes)
        is_ctor_like = in_class and short in (scope.classes[-1], "~" + scope.classes[-1])
        if not qparts and _CAPS.match(short) and not has_type and not is_ctor_like:
            self.macro_body(start, m, open_i, cl, k, close, scope, short)
            return True
        if not self.cpp and qparts:
            return False
        qparts = [p for p in qparts if p not in self.ns_seen and p not in scope.ns]
        chain = scope.classes + tuple(qparts)
        qn = ".".join(chain + (short,))
        kind = "method" if chain else "function"
        words = set(re.findall(r"[A-Za-z_]\w*", prefix))
        is_static = "static" in words
        trailing = hs[cl + 1:]
        virtual = "virtual" in words or bool(re.search(r"\b(?:override|final)\b", trailing))
        pub = not is_static and not scope.anon and (not in_class or scope.access == "public")
        line = self.m.line(start + m.start("last"))
        if chain:
            linkage = "cpp"
        elif is_static or scope.anon:
            linkage = "internal"
        elif not self.cpp:
            linkage = "c"
        else:
            linkage = "c" if scope.ext_c or re.match(r"\s*extern\s*\"", h) else "cpp"
        d = self.add_def(Def(qn, short, kind, "::".join(scope.ns), line, self.m.line(close), is_public=pub, virtual=virtual,
                             class_chain=chain, body=(k + 1, close), linkage=linkage))
        if in_class and scope.rec is not None and not qparts:
            scope.rec.methods[short] = scope.rec.methods.get(short, False) or virtual
        d.params = hs[open_i + 1:cl]
        # constructor initialiser lists sit between the parameters and the body
        d.spans = [(cl + 1 + start, k), (k + 1, close)]
        return True

    def macro_body(self, start: int, m: re.Match, open_i: int, cl: int, k: int, close: int, scope: _Scope, name: str) -> None:
        d = self.add_def(Def(f"<macro {name}@{self.m.line(start + m.start('last'))}>", name, "macro", "::".join(scope.ns),
                             self.m.line(start + m.start("last")), self.m.line(close), class_chain=scope.classes,
                             macro_name=name, macro_args=self.code[start + open_i + 1:start + cl],
                             macro_args_offset=start + open_i + 1, macro_line=self.m.line(start + m.start("last")),
                             body=(k + 1, close)))
        d.spans = [(k + 1, close)]

    def locals_of(self, d: Def) -> dict[str, set]:
        if d.locals is None:
            d.locals = _parse_params(d.params)
            _parse_locals(self.code[d.body[0]:d.body[1]], d.locals)
        return d.locals

    # body extraction ----------------------------------------------------------
    def scan_body(self, d: Def, lo: int, hi: int, names: set[str]) -> None:
        code = self.code
        text = code[lo:hi]
        line_of = self.m.line
        for cm in _CALL_RE.finditer(text):
            name = cm.group(1)
            if name not in names or name in _NOT_FUNC:
                continue            # a call to a name no repository symbol bears is never linked and never counted
            chain, a = _qualifier_before(text, cm.start())
            k = a - 1
            while k >= 0 and text[k] in " \t\r\n":
                k -= 1
            prev = text[k] if k >= 0 else ""
            if chain and not (prev == "." or text[max(0, k - 1):k + 1] == "->"):
                form, qualifier, recv, rl = "qualified", chain.rstrip(":"), None, None
            elif prev == "." or text[max(0, k - 1):k + 1] == "->":
                form, qualifier = "member", ""
                j = k - (2 if prev == ">" else 1)
                while j >= 0 and text[j] in " \t\r\n":
                    j -= 1
                recv, rl = None, None
                e = j
                while j >= 0 and (text[j].isalnum() or text[j] == "_"):
                    j -= 1
                ident = text[j + 1:e + 1]
                if ident and not ident[0].isdigit():
                    q = j
                    while q >= 0 and text[q] in " \t\r\n":
                        q -= 1
                    before = text[max(0, q - 1):q + 1]
                    if ident == "this":
                        recv = "this"
                    elif before in ("->",) or text[q:q + 1] == ".":
                        # `this->member.f()` is a member of the caller's class; any other chain is not provable
                        q2 = q - 2 if before == "->" else q - 1
                        while q2 >= 0 and text[q2] in " \t\r\n":
                            q2 -= 1
                        if text[max(0, q2 - 3):q2 + 1] == "this":
                            recv = ident
                    elif text[q:q + 1] != ":" and text[q:q + 1] not in (")", "]"):
                        recv = ident
                    if recv and recv != "this":
                        types = self.locals_of(d).get(recv)
                        if types is not None:
                            rl = next(iter(types)) if len(types) == 1 and None not in types else False
                            if rl is None:
                                rl = False
            else:
                if prev and (prev.isalnum() or prev == "_"):
                    j = k
                    while j >= 0 and (text[j].isalnum() or text[j] == "_"):
                        j -= 1
                    word = text[j + 1:k + 1]
                    if word not in _CALL_AFTER:
                        continue  # `Foo x(1)`, `new Foo(...)`: a declaration or an implicit constructor call
                form, qualifier, recv, rl = "bare", "", None, None
            self.calls.append(Call(d.index, name, form, qualifier, recv, rl, line_of(lo + cm.start())))
        self.errors_in(d, lo, text)

    def errors_in(self, d: Def, lo: int, text: str) -> None:
        line_of = self.m.line
        for m in _THROW.finditer(text):
            end = _stmt_end(text, m.end())
            expr = text[m.end():end].strip()
            if not expr:
                continue            # `throw;` rethrow
            line = line_of(lo + m.start())
            if _LITERAL_CHAIN.match(expr):
                self.errors.append(ErrorSite(d.index, "raises", "literal", self.literal(lo + m.end() + text[m.end():].index(expr), expr), "cpp-throw", line))
                continue
            tm = re.match(r"(?P<t>(?:::)?" + _IDENT + r"(?:\s*::\s*" + _IDENT + r")*)\s*(?P<o>[({])", expr)
            if tm:
                o = tm.group("o")
                cl = _match_close(expr, tm.end() - 1, o, ")" if o == "(" else "}")
                args = expr[tm.end():cl] if cl is not None else ""
                first = _split_top(args)[0] if args.strip() else ""
                if first and _LITERAL_CHAIN.match(first):
                    base = lo + m.end() + text[m.end():].index(expr) + tm.end()
                    self.errors.append(ErrorSite(d.index, "raises", re.sub(r"\s", "", tm.group("t")).lstrip(":"),
                                                 self.literal(base, first), "cpp-throw", line))
                    continue
            self.errors.append(ErrorSite(d.index, "unattributed", "throw", None, "cpp-throw", line))
        for m in _ASSERT.finditer(text):
            o = m.end() - 1
            cl = _match_close(text, o, "(", ")")
            if cl is None:
                continue
            inner = text[o + 1:cl]
            pieces = [p for p in re.split(r"&&", _flatten(inner))]
            if len(pieces) < 2:
                continue
            last = pieces[-1]
            line = line_of(lo + m.start())
            if _LITERAL_CHAIN.match(last):
                base = lo + o + 1 + inner.rfind(last.strip())
                self.errors.append(ErrorSite(d.index, "raises", "assert", self.literal(base, last.strip()), "cpp-assert", line))
            elif re.match(r"^\s*[A-Za-z_][\w.\->:()]*(?:\s*\+.*)?\s*$", last) and not re.search(r"[<>=!]", last.replace("->", "")):
                self.errors.append(ErrorSite(d.index, "unattributed", "assert", None, "cpp-assert", line))
        for m in _LOGMACRO.finditer(text):
            o = m.end() - 1
            cl = _match_close(text, o, "(", ")")
            if cl is None:
                continue
            first = _split_top(text[o + 1:cl])[0]
            if _LITERAL_CHAIN.match(first):
                base = lo + o + 1
                self.errors.append(ErrorSite(d.index, "logs", m.group(1), self.literal(base, first), "cpp-log-macro", line_of(lo + m.start())))

    def literal(self, base: int, expr: str) -> str:
        """Concatenated raw text of the adjacent string literals in `expr`, which starts at offset `base`."""
        out = []
        for q in re.finditer(r"\"[^\"]*\"", expr):
            out.append(self.m.literals.get(base + q.start(), ""))
        return "".join(out)


_CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:<[\w\s:,*]*(?:<[\w\s:,*]*>[\w\s:,*]*)*>\s*)?\(")


def _qualifier_before(text: str, a: int) -> tuple[str, int]:
    """(`A::B`, offset where the qualified name starts) for the identifier at `a`; ("", a) when it is not qualified."""
    parts: list[str] = []
    start = a
    while True:
        j = start - 1
        while j >= 0 and text[j] in " \t\r\n":
            j -= 1
        if not (j >= 1 and text[j] == ":" and text[j - 1] == ":"):
            break
        j -= 2
        while j >= 0 and text[j] in " \t\r\n":
            j -= 1
        if j >= 0 and text[j] == ">":              # `Foo<int>::bar`: skip the template arguments
            depth = 0
            while j >= 0:
                depth += (text[j] == ">") - (text[j] == "<")
                j -= 1
                if depth == 0:
                    break
            while j >= 0 and text[j] in " \t\r\n":
                j -= 1
        e = j
        while j >= 0 and (text[j].isalnum() or text[j] == "_"):
            j -= 1
        ident = text[j + 1:e + 1]
        if not ident or ident[0].isdigit():
            break                                  # a leading `::` (global scope): not a qualifier
        parts.append(ident)
        start = j + 1
    return "::".join(reversed(parts)), start


_THROW = re.compile(r"\bthrow\b")
_ASSERT = re.compile(r"\bassert\s*\(")
LOG_MACROS = ("LOG_ERR", "LOG_WRN", "LOG_ERROR", "LOG_WARN", "LOGE", "LOGW", "ERR", "ERROR", "pr_err", "pr_warn", "perror")
_LOGMACRO = re.compile(r"\b(" + "|".join(LOG_MACROS) + r")\s*\(")


def _flatten(s: str) -> str:
    """The text of `s` with every bracketed group replaced by spaces, so a top-level `&&` can be split on."""
    out, depth = [], 0
    for ch in s:
        if ch in "([{":
            depth += 1
            out.append(ch if depth == 1 else " ")
        elif ch in ")]}":
            out.append(ch if depth == 1 else " ")
            depth -= 1
        else:
            out.append(ch if depth <= 0 else " ")
    return "".join(out)


def _stmt_end(text: str, i: int) -> int:
    depth = 0
    n = min(len(text), i + 4000)
    for k in range(i, n):
        ch = text[k]
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
            if depth < 0:
                return k
        elif ch == ";" and depth <= 0:
            return k
    return n


_IND = re.compile(
    r"(?:(?<!&)&(?!&)|(?<![=!<>+\-*/%&|^])=(?!=)|[,({])\s*(?P<ref>" + _IDENT + r"(?:\s*::\s*" + _IDENT + r")*)\s*(?=[,);}])"
)


def extract_file(path: str, text: str, includer_languages: list[str] | None = None) -> FileRecords:
    """Pass 1 for one file. `includer_languages` (languages of the files that include a `.h`) is the header rule's input."""
    m = mask_source(text)
    language, consumed = file_language(path, m, includer_languages)
    cpp = language == "cpp"
    ns_seen = set(re.findall(r"\bnamespace\s+(" + _IDENT + r")", m.code)) if cpp else set()
    sc = _Scanner(path, m, cpp, ns_seen)
    sc.walk(0, len(m.code), _Scope())
    # Pass 1 ends here: definitions only. Calls, errors and indirect references need the repository's symbol names
    # (a call to a name no symbol bears is never linked or counted), so `scan_bodies` runs once all files are read.
    return FileRecords(path, cpp, sc.defs, sc.classes, sc.calls, sc.errors, [],
                       {n for n, _b, _l in m.defines}, ns_seen, m.includes, m, sc, consumed)


def scan_bodies(rec: FileRecords, names: set[str], function_names: set[str]) -> None:
    """Pass 2: call sites of `names`, error sites, and indirect references to `function_names`."""
    sc = rec.scanner
    for d in rec.defs:
        for lo, hi in d.spans:
            if hi > lo:
                sc.scan_body(d, lo, hi, names)
    m = rec.masked
    for im in _IND.finditer(m.code):
        ref = im.group("ref")
        if "::" in ref:
            ref = ref.rsplit("::", 1)[-1].strip()
        if ref in function_names:
            rec.indirect.append((ref, m.line(im.start("ref")), -1))


def indirect_refs(rec: FileRecords, function_names: set[str]) -> list[tuple[str, int, int]]:
    """Indirect references (a repository function's name used without a call) with their enclosing def index.

    A name the enclosing function or class declares as a variable, parameter or member is not a function reference.
    Names inside `#define` bodies always count: the macro may call them."""
    spans = sorted((d.body[0], d.body[1], d.index) for d in rec.defs if d.body[1] > d.body[0])
    out: list[tuple[str, int, int]] = []
    m = rec.masked
    members: set[str] = set()
    for c in rec.classes:
        members.update(c.members)
    for name, line, _ in rec.indirect:
        if name not in function_names:
            continue
        owner = -1
        for a, b, idx in spans:
            if m.line(a) <= line <= m.line(b):
                owner = idx
                break
        if owner >= 0 and name in rec.scanner.locals_of(rec.defs[owner]):
            continue
        if name in members:
            continue
        # a function's own definition or declaration is never a reference to it
        out.append((name, line, owner))
    for dname, body, line in m.defines:
        for ref in re.findall(_IDENT, body):
            if ref in function_names and ref != dname:
                out.append((ref, line, -1))
    return out


@dataclass
class Symbolic:
    """One definition after overload merging: the node `cpp_graph` writes."""
    qn: str
    short: str
    kind: str
    namespace: str
    line_start: int
    line_end: int
    overload_lines: list[int]
    is_public: bool
    virtual: bool
    class_chain: tuple[str, ...]
    def_indexes: list[int]
    framework: str | None = None
    linkage: str = ""


def finalize(rec: FileRecords) -> dict[str, Symbolic]:
    """Merge overloads into one node per qualified name; prefix the namespace where two namespaces collide (ADR D5, §2)."""
    ns_of: dict[str, set[str]] = {}
    for d in rec.defs:
        if d.kind != "macro":
            ns_of.setdefault(d.qn, set()).add(d.namespace)
    out: dict[str, Symbolic] = {}
    for d in rec.defs:
        if d.kind == "macro":
            continue
        qn = d.qn
        if len(ns_of[qn]) > 1 and d.namespace:
            qn = d.namespace.replace("::", ".") + "." + qn
        s = out.get(qn)
        if s is None:
            out[qn] = Symbolic(qn, d.short, d.kind, d.namespace, d.line, d.line_end, [d.line], d.is_public, d.virtual,
                               d.class_chain, [d.index], None, d.linkage)
        else:
            s.overload_lines.append(d.line)
            s.line_end = max(s.line_end, d.line_end)
            s.is_public = s.is_public or d.is_public
            s.virtual = s.virtual or d.virtual
            s.def_indexes.append(d.index)
            if d.linkage == "c" or not s.linkage:
                s.linkage = d.linkage
    for s in out.values():
        s.overload_lines = sorted(set(s.overload_lines))[:20]
    return out
