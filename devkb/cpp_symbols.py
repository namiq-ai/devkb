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
    "C/C++ limits: a repository macro's calls are expanded at its uses in the files that define it or include its header, until an `#undef` (#290), but a "
    "definition a macro generates is not seen; overloads are told apart by argument count only, so two of the same count share one "
    "choice (#291); receivers are resolved through declared types, smart pointers, members, one level of chaining and TEST_F/TEST_P "
    "fixtures, but there is no general type inference (a call through `auto`, an alias or an untyped receiver is not attributed); "
    "constructors are linked where written (`T x(args)`, `T x{args}`, `T(args)`, `new T(args)`, `make_unique<T>`, member and base "
    "initialisers) and picked by argument count, but an implicit construction (a default `T x;`, a copy, a move, a conversion) is not "
    "linked (#119); template instantiation is not followed (a call on a template's parameter type is not attributed); vendored and generated paths are not read; "
    "error-return codes (`return -EINVAL`, `return Status::Corruption(...)`) are not attributed; "
    "pybind11 class bindings (`py::class_`) are not read."
)

# The C profile's limits (ADR-DEVKB-009 §2): what a C pack cannot see. No overloads or receivers here: C has none.
C_LIMITS_TEXT = (
    "C limits: a repository macro's calls are expanded at its uses, but a definition a macro generates is not seen; a call through a "
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
    alts: list[tuple[int, int]] = field(default_factory=list)     # sorted spans of `#elif`/`#else` branches (not of `#if 0`); nested ones too
    undefs: list[tuple[str, int]] = field(default_factory=list)   # (name, 1-based line) of each `#undef` (#290)

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
    undefs: list[tuple[str, int]] = []
    spans: list[tuple[int, int]] = []
    stack: list[bool] = []
    gstack: list[int | None] = []      # per open conditional: start of a positive `__cplusplus` region, else None
    guards: list[tuple[int, int]] = []
    conds: list[tuple[int, str]] = []
    skipping: int | None = None
    skip_from = 0
    astack: list[int | None] = []       # per open conditional: start of its current `#elif`/`#else` branch; -1 after `#if 0`
    alts: list[tuple[int, int]] = []
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
            zero = word == "if" and re.match(r"\s*#\s*if\s*\(?\s*0\s*\)?\s*$", body.split("\\\n")[0])
            astack.append(-1 if zero else None)
            if skipping is None and zero:
                skipping, skip_from = len(stack), d.end()
        elif word in ("else", "elif", "endif"):
            if astack:
                if astack[-1] is not None and astack[-1] >= 0:
                    alts.append((astack[-1], d.start()))
                if word == "endif":
                    astack.pop()
                elif astack[-1] != -1:
                    astack[-1] = d.end()
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
        elif word == "undef":
            um = re.match(r"\s*#\s*undef\s+([A-Za-z_]\w*)", body)
            if um:
                undefs.append((um.group(1), bisect_right(line_starts, d.start())))
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
    alts.sort()
    return Masked(code, literals, defines, includes, line_starts, guards, conds, alts, undefs)


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
    class_ns: str | None = None     # methods: the namespace the class is looked up from; None when a qualifier named one (#93)
    ret: tuple[str, str] | None = None   # the declared return type (type, ptr) when it is a plain or smart-pointer type (#120)


@dataclass
class ClassRec:
    qn: str
    kind: str
    line: int
    bases: list[str] = field(default_factory=list)
    members: dict[str, tuple[str, str] | None] = field(default_factory=dict)
    methods: dict[str, bool] = field(default_factory=dict)   # declared or defined method name -> virtual?
    namespace: str = ""             # the enclosing namespace, `a::b` (#93)


@dataclass
class Call:
    caller: int          # index into FileRecords.defs
    name: str
    form: str            # bare | qualified | member
    qualifier: str       # `A::B` for qualified, else ""
    recv: str | None     # receiver identifier for member calls (`this` included), None when not a plain identifier
    recv_local: object   # (type, ptr) when the receiver is a provable local/param, False when local but unprovable, None when not local
    line: int
    argc: int = -1       # arguments written at the call (#120, F5); -1 when not counted
    chained: tuple | None = None   # `r.g().f()`: (inner receiver or "" for a bare `g()`, "g", inner recv_local) (#120, F4)
    field_of: tuple | None = None  # `b.m.f()` / `b->m->f()`: (b, b's recv_local, "m") (#120, F4)
    arg_type: str | None = None    # the declared type (short name) of the one plain argument (`x`, `*p`, `std::move(x)`), when known: a same-typed one is a copy or a move (#119)
    init: bool = False             # the name of a constructor's initialiser (`: m(x)`): a member initialisation, or a base-class constructor call (#145)


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
# a built-in type written before `(` starts a parenthesised declarator (`void (*f)(int)`); it never names a function
_BUILTIN_TYPES = {"void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "bool", "_Bool",
                  "wchar_t", "char8_t", "char16_t", "char32_t", "const", "volatile", "struct", "union", "enum"}

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


_LEADING_MACRO = re.compile(r"\s*([A-Z][A-Z0-9_]{2,})\b(?!\s*\()(?=\s+(?:namespace|class|struct|union|enum|template|extern|inline)\b)")


def _strip_decor(h: str) -> str:
    """Attributes, access specifiers and a leading `template<...>` blanked, offsets preserved."""
    for m in list(_ATTR.finditer(h)):
        h = _blank_span(h, m.start(), m.end())
    for m in list(_ACCESS.finditer(h)):
        h = _blank_span(h, m.start(), m.end())
    while True:
        m = re.match(r"\s*template\s*<", h)
        if not m:
            # a project's namespace or export macro written before a declaration keyword (`FMT_BEGIN_NAMESPACE namespace detail`,
            # `FMT_EXPORT class K`): the macro is decoration, and left in it turns the head into one unknown construct (#121)
            mm = _LEADING_MACRO.match(h)
            if not mm:
                break
            h = _blank_span(h, 0, mm.end(1))
            continue
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


def _match_close_first_branch(code: str, open_i: int, limit: int, alts: list[tuple[int, int]]) -> int | None:
    """Offset of the `}` closing the `{` at `open_i` when the braces inside `#elif`/`#else` branches are not counted, or
    None. Used only when plain matching fails: two variants of a signature or of a block opener under `#ifdef`/`#else`
    open one `{` each but share one `}` (#64); reading the first branch alone pairs them as one configuration would."""
    # a branch that already holds `open_i` is the one being read: only branches starting after it are left out. Branches
    # nest or are disjoint, so those form one union of disjoint spans.
    skip: list[tuple[int, int]] = []
    for a, b in alts[bisect_right(alts, (open_i, len(code) + 1)):]:
        if a >= limit:
            break
        if skip and a <= skip[-1][1]:
            skip[-1] = (skip[-1][0], max(skip[-1][1], b))
        else:
            skip.append((a, b))
    depth = 0
    for m in _BR["{"].finditer(code, open_i, limit):
        p = m.start()
        i = bisect_right(skip, (p, len(code) + 1)) - 1
        if i >= 0 and p < skip[i][1]:
            continue
        depth += 1 if m.group() == "{" else -1
        if depth == 0:
            return p
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
# the declared name never starts inside the type's identifier (`Tasks` is not a `Task` named `s`, #62)
_VAR_NAME = r"(?<![\w])(?P<name>" + _IDENT + r")"
_PARAM = re.compile(
    r"^\s*(?:(?:const|volatile|struct|class|union|enum|unsigned|signed|register|typename)\s+)*" + _VAR_TYPE
    + r"\s*" + _VAR_NAME + r"?\s*(?:\[[^\]]*\])?\s*$", re.S)
_LOCAL = re.compile(
    r"(?:^|[;{}(])\s*(?:(?:const|static|volatile|register|struct|class|union|enum|typename|extern|mutable|constexpr|"
    r"thread_local|unsigned|signed)\s+)*" + _VAR_TYPE + r"\s*" + _VAR_NAME + r"\s*(?=[=;,\[({)])")
_TEMPL_LOCAL = re.compile(r">\s*[*&]*\s*(" + _IDENT + r")\s*(?=[=;({,])")


def _ptr_norm(ptr: str) -> str:
    return re.sub(r"\s|const", "", ptr)


def _decl_type(m: re.Match) -> tuple[str, str] | None:
    t = m.group("type").lstrip(":")
    if t in _TYPE_KEYWORDS or t in ("auto", "void", "int", "char", "long", "short", "float", "double", "bool", "size_t"):
        return None
    p = _ptr_norm(m.group("ptr"))
    return (t, p) if p in ("", "*", "&", "&&") else None


_SMART = re.compile(r"(?:\bstd\s*::\s*)?\b(?:unique_ptr|shared_ptr)\s*<\s*(?P<type>(?:::)?" + _IDENT + r"(?:::" + _IDENT
                    + r")*)\s*>\s*(?:const\s*)?[*&]*\s*" + _VAR_NAME + r"\s*(?=[=;,\[({)]|$)")
_AUTO = re.compile(r"\bauto\s*(?P<ptr>[*&]*)\s*" + _VAR_NAME + r"\s*=\s*(?:new\s+(?P<new>" + _IDENT + r"(?:::" + _IDENT + r")*)"
                   r"|(?:std\s*::\s*)?make_(?:unique|shared)\s*<\s*(?P<make>" + _IDENT + r"(?:::" + _IDENT + r")*)\s*>"
                   r"|(?P<ctor>" + _IDENT + r"(?:::" + _IDENT + r")*)\s*[({])")


def _smart(text: str) -> tuple[str, tuple[str, str]] | None:
    """`std::unique_ptr<T> x` / `std::shared_ptr<T>& x`: (x, (T, "*")) (#120, F4)."""
    m = _SMART.search(text)
    return (m.group("name"), (m.group("type").lstrip(":"), "*")) if m else None


def _parse_params(text: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for p in _split_top(text):
        p = p.split("=", 1)[0]
        if not p.strip() or p.strip() == "void":
            continue
        sm = _smart(p)
        if sm:
            out.setdefault(sm[0], set()).add(sm[1])
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
        if m.group("type") in _TYPE_KEYWORDS or m.group("type") == "auto":
            continue                       # `auto x = ...` is read below, from its initialiser
        into.setdefault(m.group("name"), set()).add(_decl_type(m))
    smart_ends = set()
    for m in _SMART.finditer(body):        # `std::unique_ptr<T> x`: a T (#120, F4)
        into.setdefault(m.group("name"), set()).add((m.group("type").lstrip(":"), "*"))
        smart_ends.add(m.end("name"))
    for m in _TEMPL_LOCAL.finditer(body):
        if m.end(1) not in smart_ends:
            into.setdefault(m.group(1), set()).add(None)
    for m in re.finditer(r"\bauto\s*[*&]*\s*(" + _IDENT + r")\s*=", body):
        a = _AUTO.match(body, m.start())   # `auto x = T(...)`, `new T`, `make_unique<T>()`; any other initialiser: unknown
        t = a and (a.group("new") or a.group("make") or a.group("ctor"))
        into.setdefault(m.group(1), set()).add((t, "*" if a.group("new") or a.group("make") else "") if t else None)


def _return_type(prefix: str) -> tuple[str, str] | None:
    """The declared return type written before a function's name, when it is one plain type or a smart pointer (#120)."""
    p = re.sub(r"\b(?:virtual|static|inline|constexpr|explicit|friend|extern|consteval|template\s*<[^>]*>)\b", " ", prefix).strip()
    sm = re.fullmatch(r"(?:const\s+)?(?:std\s*::\s*)?(?:unique_ptr|shared_ptr)\s*<\s*((?:::)?" + _IDENT + r"(?:::" + _IDENT + r")*)\s*>\s*[&*]?", p)
    if sm:
        return (sm.group(1).lstrip(":"), "*")
    m = re.fullmatch(r"(?:const\s+)?" + _VAR_TYPE + r"\s*", p)
    return _decl_type(m) if m else None


def _norm_name(text: str) -> str:
    if text.isidentifier():
        return text
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"\s*(::|~)\s*", r"\1", text)
    if text.endswith(" "):
        text = text.strip()
    return re.sub(r"operator\s*([^\w\s])", r"operator\1", re.sub(r"operator\s*(\(\s*\)|\[\s*\])", lambda m: "operator" + re.sub(r"\s", "", m.group(1)), text))


_INIT_TAIL = re.compile(r"(?<!:)([:,])(?!:)\s*(?:::)?" + _IDENT + r"(?:\s*::\s*" + _IDENT + r")*\s*(?:" + _TARGS + r")?\s*$")
_INIT_COLON = re.compile(r"\)\s*(?:(?:noexcept|try)\b\s*(?:\([^)]*\)\s*)?)*:(?!:)")


def _init_brace(head: str) -> bool:
    """Whether the `{` after `head` opens a brace initialiser in a constructor's initialiser list (`K() : m_x{1}`, #63):
    `head` ends with a member or base name right after the list's `:` or a `,`, and a parameter list's `)` precedes
    that `:`. A class's base list (`struct C : A, B {`) has no `)` before its `:`."""
    m = _INIT_TAIL.search(head)
    return bool(m and _INIT_COLON.search(head, 0, m.end(1)))


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
        self.ns_paths: set[str] = set()      # every named namespace this file opens, as `a::b` (#93)
        self.aliases: set[str] = set()       # names a using-declaration, alias or typedef introduces (#93)

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
                if close is None and self.m.alts:
                    close = _match_close_first_branch(code, k, hi, self.m.alts)
                unmatched = close is None
                if close is None:
                    close = hi
                if self.cpp and not unmatched and _init_brace(code[start:k]):
                    i = close + 1      # `K() : m_x{1}, ...`: a member's brace initialiser; the body is a later `{`
                    continue
                end = self.brace(start, k, close, scope, unmatched)
                i = start = close + 1 if end is None else end
        # trailing statement without terminator: ignore

    def brace(self, start: int, k: int, close: int, scope: _Scope, unmatched: bool = False) -> int | None:
        """Read the construct whose `{` is at `k`. Returns where walking resumes, or None for just after `close`.

        `unmatched`: no `}` closes this `{` before `close` (typically two signature variants under `#ifdef`/`#else`, #64).
        A namespace, `extern "C"` block or class is still walked to `close`, so what it contains is read; a function,
        macro body or enum is not read at all, and walking resumes just inside its `{`, rather than letting one
        definition swallow, and take the calls of, the rest of the file."""
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
                    for i in range(1, len(chain) + 1):
                        self.ns_paths.add("::".join(scope.ns + chain[:i]))
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
            if unmatched:
                return k + 1
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
                    rec = ClassRec(qn, kw, self.m.line(pos), namespace="::".join(scope.ns))
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
        if unmatched:
            return k + 1
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
        # a trailing annotation macro (`T* const x GUARDED_BY(mu);`) is not part of a member's declaration (#120)
        h = re.sub(r"^([^()]*\w)\s+[A-Z][A-Z0-9_]*\s*\([^()]*\)\s*$", r"\1", h)
        if "(" in h:
            mm = next((c for c in _CAND.finditer(h) if _norm_name(c.group("last")) not in _NOT_FUNC), None)
            if mm is not None and not mm.group("qual").strip():
                short = _norm_name(mm.group("last"))
                if short not in _NOT_FUNC:
                    rec.methods[short] = rec.methods.get(short, False) or bool(re.search(r"\bvirtual\b|\boverride\b", h))
            return
        sm = _smart(h.split("=", 1)[0])
        if sm and re.match(r"\s*(?:(?:mutable|static|const)\s+)*(?:std\s*::\s*)?(?:unique_ptr|shared_ptr)\b", h):
            rec.members[sm[0]] = sm[1]
            return
        fm = re.match(r"^\s*(?:(?:mutable|static|const|volatile|constexpr|inline|thread_local|struct|class|enum)\s+)*" + _VAR_TYPE
                      + r"\s*" + _VAR_NAME + r"\s*(?:\[[^\]]*\])?\s*(?:=.*|\{.*|:\s*\d+)?\s*$", h, re.S)
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
            if last in _BUILTIN_TYPES and not m.group("qual").strip() and not re.search(r"\boperator\b[\w\s]*$", hs[:m.start()]):
                # `void (*name...)`: a type, then a declarator in parentheses; the name is inside (#92). `int (ns::f)(...)`
                # (a name parenthesised against a macro) loses its parentheses, so the name is read as written.
                if re.fullmatch(r"\s*" + _IDENT + r"(?:\s*::\s*" + _IDENT + r")*\s*", hs[open_i + 1:cl]) and re.match(r"\s*\(", hs[cl + 1:]):
                    hs = hs[:open_i] + " " + hs[open_i + 1:cl] + " " + hs[cl + 1:]
                pos = open_i + 1
                continue
            qual_empty = not m.group("qual").strip()
            tail = hs[cl + 1:]
            if re.search(r"(?<![=!<>])=(?!=)", _flatten(tail)):
                return False       # `void (*tab[])(void) = { a, b };`: an initialiser, not a body (#92)
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
        kept = [p for p in qparts if p not in self.ns_seen and p not in scope.ns]
        class_ns = "::".join(scope.ns) if len(kept) == len(qparts) else None   # `ns::K::f`: K's namespace is not read here
        qparts = kept
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
                             class_chain=chain, body=(k + 1, close), linkage=linkage, class_ns=class_ns))
        if in_class and scope.rec is not None and not qparts:
            scope.rec.methods[short] = scope.rec.methods.get(short, False) or virtual
        d.params = hs[open_i + 1:cl]
        d.ret = _return_type(prefix)
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
    def _arg_type(self, d: Def, text: str, open_i: int) -> str | None:
        """The declared type (short name) of the one argument written at `open_i` when it is a plain variable, `*p` of a pointer, or either inside
        `std::move(...)` / `std::forward<..>(...)`; "" for a `std::move(...)` of something untyped (a move, whatever the type); else None."""
        close = _match_close(text, open_i, text[open_i], ")" if text[open_i] == "(" else "}")
        arg = text[open_i + 1:close].strip() if close is not None else ""
        moved = re.match(r"(?:std\s*::\s*)?(?:move|forward)\s*(?:<[^>]*>)?\s*\((.*)\)\s*$", arg, re.S)
        if moved:
            arg = moved.group(1).strip()
        m = re.fullmatch(r"\*?\s*([A-Za-z_]\w*)", arg)
        types = self.locals_of(d).get(m.group(1)) if m else None
        if types and len(types) == 1 and next(iter(types)) is not None:
            return next(iter(types))[0].split("::")[-1]
        return "" if moved else None

    def _is_copy_or_move(self, d: Def, text: str, open_i: int, type_name: str) -> bool:
        """The one argument at `open_i` is `std::move(x)` / `std::forward<..>(x)`, or a variable (or `*p`) whose declared type is `type_name`."""
        t = self._arg_type(d, text, open_i)
        return t == "" or t == type_name

    def constructs_in(self, d: Def, lo: int, text: str, names: set[str], expressions_only: bool = False) -> None:
        """Constructor calls written without a call's `name(`: `new T(args)`, `T x(args)` / `T x{args}`, `make_unique<T>(args)` / `make_shared<T>`
        (SPEC-DKB-004 F3, #119). Kept as a `construct` call of the type's short name; the resolver links it when `T` is the one repository class of
        that name, and to the one constructor its argument count selects."""
        line_of = self.m.line
        if getattr(self, "has_ctor_filter", False) and (not self.ctor_re or self.ctor_re.isdisjoint(_IDENT_RE.findall(text))):
            return
        for rx, kind in ((_CTOR_NEW, "new"), (_CTOR_NEW_BARE, "newbare"), (_CTOR_MAKE, "make"), (_CTOR_LOCAL, "local"), (_CTOR_DEFAULT, "default")):
            if expressions_only and kind in ("local", "default"):
                continue
            for cm in rx.finditer(text):
                qual, name = cm.group(1), cm.group(2)
                if name not in names or name in _NOT_FUNC or name in _NOT_TYPE or (kind == "local" and qual.strip() == "" and name in _NOT_TYPE):
                    continue
                if kind in ("default", "newbare"):      # `T x;`, `new T;`, `new T[n]`: the default constructor, written nowhere; `extern T x;` declares, it does not construct
                    if kind == "default" and re.search(r"\bextern\b", cm.group(0)):
                        continue
                    c = Call(d.index, name, "construct", re.sub(r"\s", "", qual).rstrip(":"), None, None, line_of(lo + cm.start(2)), 0)
                    self.calls.append(c)
                    continue
                open_i = cm.end() - 1
                c_argc = _argc(text, open_i)
                if c_argc == 1 and self._is_copy_or_move(d, text, open_i, name):
                    continue            # `T copy(other)`, `T moved(std::move(other))`: an implicit copy or move, not a declared constructor
                c = Call(d.index, name, "construct", re.sub(r"\s", "", qual).rstrip(":"), None, None, line_of(lo + cm.start(2)), c_argc)
                self.calls.append(c)

    def scan_body(self, d: Def, lo: int, hi: int, names: set[str], init: bool = False) -> None:
        code = self.code
        text = code[lo:hi]
        line_of = self.m.line
        members = _initialiser_names(text) if init else set()
        has_mock = "EXPECT_CALL" in text or "ON_CALL" in text      # one substring test per body, not a regex search per call
        for cm in _CALL_RE.finditer(text):
            name = cm.group(1)
            is_init = cm.start(1) in members      # `: m(x), n(f(x))`: m and n are initialised, not called (#145); `f` is not at depth 0, so it is read
            if (name not in names and not is_init) or name in _NOT_FUNC:
                continue            # a call to a name no repository symbol bears is never linked and never counted (an initialiser may name a data member: #119)
            if has_mock and _in_mock_method_slot(text[max(0, cm.start() - 300):cm.start()]):
                continue            # `EXPECT_CALL(mock, allocate(1))`: the method the mock expects, not a call to a repository `allocate` (#146)
            chain, a = _qualifier_before(text, cm.start())
            k = a - 1
            while k >= 0 and text[k] in " \t\r\n":
                k -= 1
            prev = text[k] if k >= 0 else ""
            if chain and not (prev == "." or text[max(0, k - 1):k + 1] == "->"):
                form, qualifier, recv, rl = "qualified", chain.rstrip(":"), None, None
            elif prev == "." or text[max(0, k - 1):k + 1] == "->":
                form, qualifier = "member", ""
                chained = field_of = None
                j = k - (2 if prev == ">" else 1)
                while j >= 0 and text[j] in " \t\r\n":
                    j -= 1
                recv, rl = None, None
                chained = _chained_before(text, j) if j >= 0 and text[j] == ")" else None
                if chained is not None:            # `r.g().f()`: f's receiver is what g returns (#120, F4)
                    irecv = chained[0]
                    irl = None
                    if irecv and irecv != "this":
                        types = self.locals_of(d).get(irecv)
                        if types is not None:
                            irl = next(iter(types)) if len(types) == 1 and None not in types else False
                    chained = (irecv, chained[1], irl)
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
                        # `this->member.f()` is a member of the caller's class; `b.m.f()`: m is a member of b's class
                        q2 = q - 2 if before == "->" else q - 1
                        while q2 >= 0 and text[q2] in " \t\r\n":
                            q2 -= 1
                        if text[max(0, q2 - 3):q2 + 1] == "this":
                            recv = ident
                        else:
                            b2 = q2
                            while b2 >= 0 and (text[b2].isalnum() or text[b2] == "_"):
                                b2 -= 1
                            base = text[b2 + 1:q2 + 1]
                            pre = text[max(0, b2 - 1):b2 + 1]
                            if base and not base[0].isdigit() and pre != "->" and text[b2:b2 + 1] not in (".", ")", "]", ":"):
                                types = self.locals_of(d).get(base)
                                brl = None if types is None else (next(iter(types)) if len(types) == 1 and None not in types else False)
                                field_of = (base, brl, ident)
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
                elif prev in ">*&" and self.cpp and _DECL_PREFIX.match(text, _stmt_start(text, k), a):
                    continue      # `std::vector<int> x(3)`, `Foo *x(p)`, `const Bar& x(y)`: a declaration, not a call (#65)
                form, qualifier, recv, rl = "bare", "", None, None
                if name == d.short and d.kind == "method" and (mm := re.search(r"\b([A-Z][A-Z0-9]*_[A-Z0-9_]*)\s*\(\s*$", text[max(0, cm.start() - 80):cm.start()])) \
                        and not mm.group(1).startswith(("ASSERT_", "EXPECT_", "CHECK_", "DCHECK_", "VERIFY_", "LIKELY", "UNLIKELY")):
                    form = "qualified"      # `FMT_POSIX(close(fd))` inside a method `close`: a macro adapts the global call; not the method itself (#95)
            c = Call(d.index, name, form, qualifier, recv, rl, line_of(lo + cm.start()), _argc(text, cm.end() - 1))
            c.init = is_init
            if is_init and c.argc == 1:
                c.arg_type = self._arg_type(d, text, cm.end() - 1)
            if form == "member" and chained is not None and recv is None:
                c.chained = chained
            if form == "member" and field_of is not None and recv is None:
                c.field_of = field_of
            self.calls.append(c)
        if self.cpp:
            self.constructs_in(d, lo, text, names, expressions_only=init)       # an initialiser list holds `new T(..)`, never a declaration
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


_MOCK_START = re.compile(r"\b(?:EXPECT_CALL|ON_CALL)\s*\(")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def _in_mock_method_slot(prefix: str) -> bool:
    """Is the text right after `prefix` the second argument of `EXPECT_CALL(mock, ` / `ON_CALL(mock, `: the one top-level comma of the macro's
    own argument list so far, however many commas the mock expression's inner calls hold (#146)."""
    starts = list(_MOCK_START.finditer(prefix))
    if not starts:
        return False
    rest = prefix[starts[-1].end():]
    depth, commas = 0, 0
    for ch in rest:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return False
        elif ch == "," and depth == 0:
            commas += 1
    return depth == 0 and commas == 1 and rest.rstrip().endswith(",")


_QUAL = r"((?:[A-Za-z_]\w*\s*::\s*)*)([A-Za-z_]\w*)"                       # `ns::T`: (qualifier with `::`, short name)
_CTOR_NEW = re.compile(r"\bnew\s+(?:\([^()]*\)\s*)?(?:::\s*)?" + _QUAL + r"\s*(?:<[^;{}()]*>)?\s*([({])")                    # `new T(args)`, `new T{args}`
_CTOR_NEW_BARE = re.compile(r"\bnew\s+(?:\([^()]*\)\s*)?(?:::\s*)?" + _QUAL + r"\s*(?:<[^;{}()]*>)?\s*(?=[;,)\]}?\[]|:(?!:)|$)")     # `new T;`, `new T[n]`, `, tmp_(new T),`: the default constructor, written nowhere (#119)
_CTOR_MAKE = re.compile(r"\b(?:std\s*::\s*)?make_(?:unique|shared)\s*<\s*(?:::\s*)?" + _QUAL + r"[^<>;{}]*(?:<[^;{}]*>)?\s*>\s*(\()")   # `make_unique<T>(args)`
_CTOR_LOCAL = re.compile(r"(?:^|(?<=[;{}]))\s*(?:(?:const|static|constexpr|volatile)\s+)*(?:::\s*)?" + _QUAL
                    + r"\s*(?:<[^;{}()]*>)?\s+(?:[&*]\s*)*[A-Za-z_]\w*\s*([({])")                                              # `T x(args);`, `T x{args};`
_CTOR_DEFAULT = re.compile(r"(?:^|(?<=[;{}]))[ \t\r\n]*(?:(?:const|static|constexpr|volatile)\s+)*(?:::\s*)?" + _QUAL
                           + r"\s*(?:<[^;{}()]*>)?\s+[A-Za-z_]\w*\s*(?:\[[^\]]*\]\s*)?(?:,\s*[A-Za-z_]\w*\s*)*;")                # `T x;`, `T x, y;`
_NOT_TYPE = frozenset("return new delete throw case else goto using typedef namespace struct class enum union sizeof co_return co_yield".split())


def _initialiser_names(text: str) -> set[int]:
    """Offsets of the names in a constructor's member-initialiser list (#145): the identifier at depth 0 after the list's `:` or after a `,`
    at depth 0. `text` is what lies between the parameter list and the body (`: m(x), n(f(x))`); a head with no `:` has none. The
    arguments of an initialiser are not names of it: `f` in `n(f(x))` is a call and stays one."""
    out: set[int] = set()
    depth, seen_colon, expect = 0, False, False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([{<" and not (ch == "<" and depth == 0):
            depth += 1 if ch != "<" else 0
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0 and text[i + 1:i + 2] != ":" and text[i - 1:i] != ":":
            seen_colon, expect = True, True
        elif ch == "," and depth == 0 and seen_colon:
            expect = True
        elif expect and (ch.isalpha() or ch == "_"):
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] in "_:"):
                j += 1
            out.add(i)
            expect = False
            i = j
            continue
        i += 1
    return out


def _argc(text: str, open_i: int) -> int:
    """The number of arguments in the call whose `(` is at open_i (masked text: no strings or comments); -1 if unclosed."""
    depth, n, seen = 0, 0, False
    for ch in text[open_i:open_i + 4000]:
        if ch in "([{":
            depth += 1
            if depth == 1:
                continue
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return n + 1 if seen else 0
        elif ch == "," and depth == 1:
            n += 1
            continue
        if depth >= 1 and not ch.isspace():
            seen = True
    return -1


def _chained_before(text: str, j: int) -> tuple[str, str] | None:
    """For `X.g(...)` / `X->g(...)` / `g(...)` ending at text[j] == ")": (X or "this" or "", "g"); None if not that shape."""
    depth = 0
    i = j
    while i >= 0:
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            depth -= 1
            if depth == 0:
                break
        i -= 1
    if i < 0:
        return None
    k = i - 1
    while k >= 0 and text[k] in " \t\r\n":
        k -= 1
    e = k
    while k >= 0 and (text[k].isalnum() or text[k] == "_"):
        k -= 1
    inner = text[k + 1:e + 1]
    if not inner or inner[0].isdigit() or inner in _NOT_FUNC:
        return None
    q = k
    while q >= 0 and text[q] in " \t\r\n":
        q -= 1
    if q >= 0 and (text[q] == "." or text[max(0, q - 1):q + 1] == "->"):
        r = q - (2 if text[q] == ">" else 1)
        while r >= 0 and text[r] in " \t\r\n":
            r -= 1
        re_ = r
        while r >= 0 and (text[r].isalnum() or text[r] == "_"):
            r -= 1
        recv = text[r + 1:re_ + 1]
        if not recv or recv[0].isdigit():
            return None
        before = text[max(0, r - 1):r + 1]
        if before in ("->",) or text[r:r + 1] in (".", ")", "]"):
            return None                     # a longer chain: one level only
        return (recv, inner)
    if q >= 0 and text[q] == ":":
        return None                         # `ns::g()`: not a receiver the rules read
    return ("", inner)


_CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:<[\w\s:,*]*(?:<[\w\s:,*]*>[\w\s:,*]*)*>\s*)?\(")


# a statement prefix that is nothing but a type, so the name after it is declared, not called (#65): `std::vector<int>`, `Foo *`
_DECL_PREFIX = re.compile(
    r"(?!.*<<)\s*(?:(?:const|static|volatile|constexpr|thread_local|mutable|register|unsigned|signed|struct|class|union|enum|typename)\s+)*"
    r"(?!(?:" + "|".join(sorted(_CALL_AFTER)) + r")\b)(?:::\s*)?" + _IDENT + r"\s*(?:" + _TARGS + r")?"
    r"(?:\s*::\s*" + _IDENT + r"\s*(?:" + _TARGS + r")?)*\s*(?:const\b\s*)?(?:[*&]\s*(?:const\b\s*)?)*\Z", re.S)


def _stmt_start(text: str, k: int) -> int:
    """Offset just after the last `;`, `{` or `}` before `k` (the start of the statement `k` is in)."""
    return max(text.rfind(";", 0, k), text.rfind("{", 0, k), text.rfind("}", 0, k)) + 1


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


# `using ns::K;`, `using K = ...;`, `typedef ... K;`: a name that may stand for a class of another namespace (#93)
_ALIAS = re.compile(r"\busing\s+(?!namespace\b)(?:typename\s+)?(?:" + _IDENT + r"\s*::\s*)+(" + _IDENT + r")\s*;|\busing\s+(" + _IDENT
                    + r")\s*=")
_TYPEDEF = re.compile(r"\btypedef\b[^;{}]*?\b(" + _IDENT + r")\s*(?:\[[^\]]*\]\s*)*;|\}\s*(" + _IDENT + r")\s*;")


def extract_file(path: str, text: str, includer_languages: list[str] | None = None) -> FileRecords:
    """Pass 1 for one file. `includer_languages` (languages of the files that include a `.h`) is the header rule's input."""
    m = mask_source(text)
    language, consumed = file_language(path, m, includer_languages)
    cpp = language == "cpp"
    ns_seen = set(re.findall(r"\bnamespace\s+(" + _IDENT + r")", m.code)) if cpp else set()
    sc = _Scanner(path, m, cpp, ns_seen)
    sc.walk(0, len(m.code), _Scope())
    if cpp:
        sc.aliases = {a or b for a, b in _ALIAS.findall(m.code) + _TYPEDEF.findall(m.code)}
    # Pass 1 ends here: definitions only. Calls, errors and indirect references need the repository's symbol names
    # (a call to a name no symbol bears is never linked or counted), so `scan_bodies` runs once all files are read.
    return FileRecords(path, cpp, sc.defs, sc.classes, sc.calls, sc.errors, [],
                       {n for n, _b, _l in m.defines}, ns_seen, m.includes, m, sc, consumed)


def scan_bodies(rec: FileRecords, names: set[str], function_names: set[str], ctor_re: frozenset | None = None) -> None:
    """Pass 2: call sites of `names`, error sites, and indirect references to `function_names`. `ctor_re` is the set of names of the classes that have
    a constructor (#119); without it, constructor calls are looked for in every body."""
    sc = rec.scanner
    sc.ctor_re = ctor_re
    sc.has_ctor_filter = True
    for d in rec.defs:
        for n, (lo, hi) in enumerate(d.spans):
            if hi > lo:
                # the first of a function's two spans lies between its `)` and `{` (an initialiser list); a macro body such as TEST(..) has one span
                # that is all body, where a `:` is a ternary or a label (#145)
                sc.scan_body(d, lo, hi, names, init=n == 0 and len(d.spans) == 2)
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
    # the owner of a line is the first body (by offset) whose lines contain it: one table, filled last-to-first so the
    # first wins, instead of a scan of every body per reference (#66)
    owner_of: dict[int, int] = {}
    for a, b, idx in reversed(spans):
        for ln in range(m.line(a), m.line(b) + 1):
            owner_of[ln] = idx
    for name, line, _ in rec.indirect:
        if name not in function_names:
            continue
        owner = owner_of.get(line, -1)
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
    class_ns: str | None = None     # see Def.class_ns; None when overloads disagree
    spans: list[tuple[int, int]] = field(default_factory=list)   # each definition's own (start, end) line range


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
                               d.class_chain, [d.index], None, d.linkage, d.class_ns, [(d.line, d.line_end)])
        else:
            s.overload_lines.append(d.line)
            s.spans.append((d.line, d.line_end))
            s.line_end = max(s.line_end, d.line_end)
            s.is_public = s.is_public or d.is_public
            s.virtual = s.virtual or d.virtual
            s.def_indexes.append(d.index)
            if d.linkage == "c" or not s.linkage:
                s.linkage = d.linkage
            if s.class_ns != d.class_ns:
                s.class_ns = None
    for s in out.values():
        s.overload_lines = sorted(set(s.overload_lines))[:20]
    return out
