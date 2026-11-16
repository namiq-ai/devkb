"""C/C++ Symbol and call extraction (stdlib only, no parser dependency).

Same trade as ts_symbols.py: a scanner, not a compiler. It masks comments, string and character literals and
preprocessor lines, then walks the braces, so a `{` in a string or a commented-out function never confuses it. It
finds function *definitions* (free functions, methods defined in a class body, `Foo::bar` defined out of line,
constructors, destructors, operators) and `class`/`struct`/`union`/`enum` definitions, nested in namespaces and
classes, and the calls inside each function body.

What it does not do, and says so rather than guess: no preprocessor expansion (a function a macro generates has no
Symbol), no overload resolution (overloads share one qualified name; a call resolves to a name, not a signature), no
type inference (`a.f()` is attributed to `f` only when exactly one `f` exists in the repository), no template
instantiation. Calls inside a lambda belong to the function that contains it.

Qualified names join with `.` (`ns.Class.method`), as Python's do, so every consumer that splits on the last `.` to
get the short name works on C++ unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path

CPP_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".h++", ".inl", ".ipp", ".tpp")
_SKIP_PARTS = re.compile(r"(^|/)(third_party|thirdparty|vendor|external|extern|deps|node_modules|build|cmake-build[^/]*|\.git)/")

_CONTROL = {"if", "for", "while", "switch", "catch", "return", "sizeof", "alignof", "alignas", "decltype", "typeid",
            "noexcept", "static_assert", "defined", "throw", "else", "do", "new", "delete", "case", "co_return",
            "co_await", "co_yield", "requires", "__attribute__", "static_cast", "dynamic_cast", "const_cast",
            "reinterpret_cast", "and", "or", "not", "using", "typedef", "template", "operator", "asm", "__asm__"}
# Test frameworks declare a test as a macro that looks like a function; it is a test case, not a Symbol.
_TEST_MACROS = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P", "TEST_CASE", "TEST_CASE_METHOD",
                "SCENARIO", "BOOST_AUTO_TEST_CASE", "BOOST_FIXTURE_TEST_CASE", "BOOST_AUTO_TEST_SUITE", "TEST_SUITE",
                "TEMPLATE_TEST_CASE", "INSTANTIATE_TEST_SUITE_P", "FIXTURE_TEST_CASE", "BOOST_AUTO_TEST_CASE_TEMPLATE"}

_SCOPE_KW = re.compile(r"\b(class|struct|union|enum(?:\s+(?:class|struct))?)\s+(?:\[\[[^\]]*\]\]\s*)*(?:[A-Z_][A-Z0-9_]*\s+)*([A-Za-z_]\w*)(?:\s+final)?\s*(?:[:{]|$)")
_NAMESPACE = re.compile(r"\bnamespace\s+([A-Za-z_][\w:]*)?\s*$")
_IDENT = re.compile(r"[A-Za-z_~]\w*")
_CALL = re.compile(r"(?<![\w$])(~?[A-Za-z_]\w*)\s*(?:<[^<>;(){}]*>)?\s*\(")
_TEST_CASE = re.compile(r"^[ \t]*(TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P|BOOST_AUTO_TEST_CASE|BOOST_FIXTURE_TEST_CASE)"
                        r"\s*\(\s*([A-Za-z_]\w*)\s*(?:,\s*([A-Za-z_]\w*))?", re.M)
_CATCH_CASE = re.compile(r"^[ \t]*(?:TEST_CASE|SCENARIO|TEMPLATE_TEST_CASE)\s*\(\s*\"([^\"\n]+)\"", re.M)


def is_cpp_path(rel: str) -> bool:
    return rel.lower().endswith(CPP_SUFFIXES) and not _SKIP_PARTS.search(rel)


def mask(src: str) -> str:
    """The source with comments, string/char literals (contents) and preprocessor lines blanked, same length and
    same newlines, so offsets and line numbers stay true."""
    out = list(src)
    n, i = len(src), 0

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    line_start = True
    while i < n:
        c = src[i]
        if c == "\n":
            line_start = True
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == "#" and line_start:  # preprocessor directive, with `\` continuations
            j = i
            while j < n:
                if src[j] == "\n" and not src[j - 1:j] == "\\" and src[max(0, j - 2):j] != "\\\r":
                    break
                j += 1
            blank(i, j)
            i = j
            continue
        line_start = False
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            blank(i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            blank(i, j)
            i = j
        elif c == "R" and src.startswith('R"', i) and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")):
            m = re.match(r'R"([^()\\ ]{0,16})\(', src[i:i + 24])
            if m:
                end = src.find(")" + m.group(1) + '"', i)
                j = n if end == -1 else end + len(m.group(1)) + 2
                blank(i + 1, j)
                i = j
            else:
                i += 1
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, min(j, n))
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _match_brace(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _strip_template(header: str) -> str:
    """Drop leading `template <...>` clauses (nesting-aware) so the declaration itself is what is left."""
    h = header.lstrip()
    while h.startswith("template"):
        m = re.match(r"template\s*<", h)
        if not m:
            break
        depth, i = 1, m.end()
        while i < len(h) and depth:
            depth += {"<": 1, ">": -1}.get(h[i], 0)
            i += 1
        h = h[i:].lstrip()
    return h


def _function_name(header: str) -> str | None:
    """The (possibly `A::b`-qualified) name of the function a header before `{` defines, else None."""
    h = _strip_template(header)
    h = re.sub(r"\[\[[^\]]*\]\]", " ", h)
    depth, open_at = 0, -1
    for i, c in enumerate(h):  # the first top-level `(` whose preceding token is a name
        if c == "(" and depth == 0:
            before = h[:i].rstrip()
            m = re.search(r"(operator\s*(?:\(\s*\)|\[\s*\]|[^\w\s(]+|\s+[\w:<>*&\s]+?)|~?[A-Za-z_]\w*)$", before)
            if m and m.group(1) not in _CONTROL and not (m.group(1).startswith("operator") and False):
                open_at = i
                name_end = len(before)
                name_start = m.start(1)
                # fold a leading `A::B::` / `A<T>::` qualifier into the name
                q = re.search(r"((?:~?[A-Za-z_]\w*(?:\s*<[^<>]*>)?\s*::\s*)+)$", before[:name_start])
                if q:
                    name_start = q.start(1)
                name = re.sub(r"\s+", "", re.sub(r"<[^<>]*>", "", before[name_start:name_end])) \
                    if not before[name_start:].startswith("operator") else re.sub(r"\s+", " ", before[name_start:]).strip()
                return name
            return None
        if c in "<":
            depth += 0
    return None


def _close_paren(text: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _is_definition_header(header: str) -> str | None:
    """The function name when `header` (the text since the last `;`, `{` or `}`) is a function definition head."""
    h = _strip_template(header).strip()
    if not h or h.startswith(("namespace", "extern \"", "do", "else", "try", "typedef", "using")) and "(" not in h:
        return None
    if re.search(r"(^|[^\w])=\s*[^=]*$", h.split("(")[0]) and "(" not in h.split("=")[0]:
        return None  # `x = {` / `auto f = [](...) {`
    m = re.search(r"\(", h)
    if not m:
        return None
    name = _function_name(h)
    if not name or name in _TEST_MACROS:
        return None
    end = _close_paren(h, h.index("(", len(h[: h.find(name.split("::")[-1])]) if False else m.start()))
    if end == -1:
        return None
    # what follows the parameter list may only be qualifiers, a trailing return type or a constructor init list
    tail = h[end + 1:].strip()
    if tail and not re.match(r"^(?:(?:const|volatile|noexcept(?:\s*\([^)]*\))?|override|final|&&?|mutable|constexpr|"
                             r"throw\s*\([^)]*\)|__attribute__\s*\(\(.*?\)\)|\[\[[^\]]*\]\])\s*)*"
                             r"(?:->[^;{}]*|:[^;{}:][^;{}]*|:)?$", tail, re.S):
        return None
    return name


def _is_ctor_init_brace(header: str) -> bool:
    """`Foo::Foo(int x) : a(x), b` followed by `{`: the brace opens `b{...}`, not the body."""
    h = _strip_template(header)
    m = re.search(r"\)\s*(?:noexcept\s*)?(?:const\s*)?:(?!:)", h)
    return bool(m and re.search(r"[\w>]\s*$", h) and not re.search(r"\)\s*(?:const\s*)?(?:noexcept\s*)?$", h))


def extract_source(src: str) -> tuple[list[dict], list[tuple[str, str, str | None, str | None]]]:
    """(symbols, calls). symbols: [{qualified_name, kind, line_start, line_end}]; calls:
    [(caller_qualified_name, callee_short_name, receiver_or_None, qualifier_or_None)]."""
    text = mask(src)
    symbols: list[dict] = []
    calls: list[tuple[str, str, str | None, str | None]] = []
    line_of = _line_index(text)

    def walk(start: int, end: int, scope: list[str], in_class: bool) -> None:
        i, header_start = start, start
        while i < end:
            c = text[i]
            if c == ";":
                header_start = i + 1
            elif c == "}":
                header_start = i + 1
            elif c == "{":
                header = text[header_start:i]
                close = _match_brace(text, i)
                if _is_ctor_init_brace(header):
                    i = close
                    continue
                stripped = _strip_template(header).strip()
                ns = _NAMESPACE.search(stripped)
                if ns is not None and "(" not in stripped:
                    parts = [p for p in (ns.group(1) or "").split("::") if p]
                    walk(i + 1, close - 1, scope + parts, False)
                elif re.match(r"^extern\s*\"[^\"]*\"\s*$|^extern\s*$", re.sub(r"\"[^\"]*\"", '""', stripped) or "x"):
                    walk(i + 1, close - 1, scope, in_class)
                else:
                    fname = _is_definition_header(header)
                    kw = _SCOPE_KW.search(stripped) if fname is None else None
                    if fname is not None:
                        qn = ".".join(scope + [p for p in fname.split("::") if p]) if not fname.startswith("operator") \
                            else ".".join(scope + [fname])
                        # a method's own class qualifies it; a nested-name definition keeps the qualifier it was given
                        a = _name_pos(text, header_start, i, fname)
                        symbols.append({"qualified_name": qn, "kind": "method" if (in_class or "::" in fname) else "function",
                                        "line_start": line_of(a), "line_end": line_of(close - 1)})
                        for call in _calls_in(text[i + 1:close - 1]):
                            calls.append((qn, *call))
                    elif kw is not None and stripped.split()[0] in ("class", "struct", "union", "enum", "typedef") \
                            or kw is not None and re.match(r"^(class|struct|union|enum)\b", stripped):
                        kind = kw.group(1).split()[0]
                        name = kw.group(2)
                        symbols.append({"qualified_name": ".".join(scope + [name]), "kind": "class" if kind != "enum" else "enum",
                                        "line_start": line_of(header_start + len(header) - len(header.lstrip())),
                                        "line_end": line_of(close - 1)})
                        if kind != "enum":
                            walk(i + 1, close - 1, scope + [name], True)
                    # anything else (initialiser, lambda at namespace scope, a block): not a Symbol
                i = close
                header_start = i
                continue
            i += 1

    walk(0, len(text), [], False)
    return symbols, calls


def _name_pos(text: str, a: int, b: int, name: str) -> int:
    j = text.find(name.split("::")[0].lstrip("~"), a, b)
    return a + (len(text[a:b]) - len(text[a:b].lstrip())) if j == -1 else j


def _line_index(text: str):
    import bisect
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    return lambda pos: bisect.bisect_right(starts, max(pos, 0))


def _calls_in(body: str) -> list[tuple[str, str | None, str | None]]:
    """(callee short name, receiver, qualifier) for each call in a function body."""
    out = []
    for m in _CALL.finditer(body):
        name = m.group(1)
        if name in _CONTROL:
            continue
        before = body[:m.start()].rstrip()
        receiver = qualifier = None
        if before.endswith("::"):
            q = re.search(r"((?:[A-Za-z_]\w*(?:\s*<[^<>]*>)?\s*::\s*)*[A-Za-z_]\w*)\s*::$", before)
            if q:
                qualifier = re.sub(r"\s+|<[^<>]*>", "", q.group(1))
        elif before.endswith((".", "->")):
            r = re.search(r"([A-Za-z_]\w*|\)|\])\s*(?:\.|->)$", before)
            receiver = r.group(1) if r and r.group(1) not in (")", "]") else "<expr>"
        elif re.search(r"\b(?:new|class|struct|enum|typename)\s*$", before):
            pass
        out.append((name, receiver, qualifier))
    return out


def extract_file(path: Path) -> tuple[list[dict], list[tuple[str, str, str | None, str | None]]]:
    try:
        return extract_source(path.read_text(errors="replace"))
    except OSError:
        return [], []


def test_cases(src: str) -> list[tuple[str, int]]:
    """[(test name, 1-based line)] for GoogleTest, Boost.Test and Catch2 cases."""
    out = []
    for m in _TEST_CASE.finditer(src):
        name = f"{m.group(2)}.{m.group(3)}" if m.group(3) else m.group(2)
        out.append((name, src.count("\n", 0, m.start()) + 1))
    for m in _CATCH_CASE.finditer(src):
        out.append((m.group(1), src.count("\n", 0, m.start()) + 1))
    return sorted(out, key=lambda t: t[1])


def resolve_call(caller_qn: str, callee: str, receiver: str | None, qualifier: str | None,
                 by_short: dict[str, list[str]]) -> tuple[str | None, float, str]:
    """(target qualified name, confidence, source tag) among the repository's qualified names with this short name
    (`by_short[short] = [qualified names]`), or (None, 0, "") when it is ambiguous or unknown. Never a guess between
    two equally good candidates."""
    cands = by_short.get(callee, [])
    if not cands:
        return None, 0.0, ""
    if qualifier:
        q = qualifier.replace("::", ".")
        hit = sorted({c for c in cands if c == f"{q}.{callee}" or c.endswith(f".{q}.{callee}")})
        return (hit[0], 0.8, "cpp-qualified") if len(hit) == 1 else (None, 0.0, "")
    if receiver is None or receiver == "this":
        cls = caller_qn.rsplit(".", 1)[0] if "." in caller_qn else ""
        while cls:  # a bare call from a method prefers the same class, then the enclosing namespaces
            hit = sorted({c for c in cands if c == f"{cls}.{callee}"})
            if len(hit) == 1:
                return hit[0], 0.8, "cpp-same-scope"
            cls = cls.rsplit(".", 1)[0] if "." in cls else ""
    if len(set(cands)) == 1:
        return cands[0], (0.5 if receiver else 0.6), "cpp-unique-name"
    return None, 0.0, ""
