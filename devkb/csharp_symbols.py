"""C# symbols and calls, with the standard library only (no Roslyn, no .NET SDK, no tree-sitter).

What it reads: tracked `.cs` files outside generated and vendored paths.
What it makes: `Symbol` nodes for types (class, struct, interface, record: kind `class`; enum: `enum`) and members
(methods, constructors, properties, operators: kind `method`; local functions: kind `function`), keyed
`path::Namespace.Type.Member`, a `DEFINED_IN` edge to the file, and `CALLS` edges between them.

How, in two passes per file (the design of `cpp_symbols.py`; SPEC-DEVKB-CSHARP §3):

1. `mask` blanks comments, every string form (regular, verbatim, interpolated with nested braces, raw), character
   literals and preprocessor lines, keeping every newline, so offsets and line numbers survive and the only braces,
   semicolons and parentheses left are code.
2. `scan_file` walks `{`, `}` and `;` with a scope stack. The text since the last `;`, `{` or `}` is the *header* of
   whatever a brace opens (a namespace, a type, a member, or a block whose calls belong to the enclosing member), or of
   what a `;` ends (a field, an interface or abstract member, an expression-bodied member `... => expr;`, a
   file-scoped `namespace A;`).

What it cannot do, and so does not guess: resolve overloads by argument types (overloads share one key, as in
Python), infer the type of an expression, follow `using static` or `dynamic`. A call becomes an edge only when exactly
one symbol can be meant (`_Index`); every other call to a name the repository defines is counted as unresolved, so a
pack says it is incomplete.
"""
from __future__ import annotations

import re
import subprocess
from bisect import bisect_left
from pathlib import Path

_SKIP = re.compile(r"(^|/)(obj|bin|node_modules|vendor|third_party|packages)/|\.g\.cs$|\.g\.i\.cs$|\.Designer\.cs$"
                   r"|(^|/)AssemblyInfo\.cs$|\.AssemblyAttributes\.cs$")
_MAX_BYTES = 2_000_000
TEST_ATTRS = frozenset({"Fact", "Theory", "Test", "TestCase", "TestCaseSource", "TestMethod", "DataTestMethod",
                        "SkippableFact", "SkippableTheory"})
_CONTROL = frozenset("""if else for foreach while do switch case default try catch finally using lock fixed checked
unchecked unsafe return throw yield await new typeof nameof sizeof stackalloc when get set init add remove
""".split())
_NOT_CALL = _CONTROL | frozenset("""base this var await is as in out ref params operator implicit explicit
delegate where select from let join orderby group into""".split())
_MODIFIERS = re.compile(r"\b(public|private|protected|internal|static|readonly|sealed|abstract|virtual|override|"
                        r"async|extern|unsafe|new|partial|const|volatile|required|file|ref|scoped)\b")


# ── pass 1: mask ─────────────────────────────────────────────────────────────

def _blank(chars: list[str], start: int, end: int) -> None:
    for k in range(start, end):
        if chars[k] != "\n":
            chars[k] = " "


def _string_end(text: str, i: int) -> int | None:
    """If a string literal starts at i (with any `$`/`@` prefix), the index just past it; else None."""
    n, k, dollars, verbatim = len(text), i, 0, False
    while k < n and text[k] in "$@":
        dollars += text[k] == "$"
        verbatim |= text[k] == "@"
        k += 1
    if k >= n or text[k] != '"' or (k > i and not text[i] in "$@"):
        return None
    if text.startswith('"""', k):                                  # raw string: N quotes ... N quotes
        q = k
        while q < n and text[q] == '"':
            q += 1
        quotes = text[k:q]
        end = text.find(quotes, q)
        return n if end < 0 else end + len(quotes)
    k += 1
    depth = 0
    while k < n:
        c = text[k]
        if depth:                                                  # inside an interpolation hole: code again
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' or (c in "$@" and k + 1 < n and text[k + 1] in '"$@'):
                inner = _string_end(text, k)
                if inner:
                    k = inner
                    continue
            elif c == "'":
                k = _char_end(text, k)
                continue
            k += 1
            continue
        if dollars and c == "{":
            if text.startswith("{{", k):
                k += 2
                continue
            depth = 1
        elif verbatim:
            if c == '"':
                if text.startswith('""', k):
                    k += 2
                    continue
                return k + 1
        else:
            if c == "\\":
                k += 2
                continue
            if c == '"' or c == "\n":
                return k + 1
        k += 1
    return n


def _char_end(text: str, i: int) -> int:
    k = i + 1
    if k < len(text) and text[k] == "\\":
        k += 2
    else:
        k += 1
    end = text.find("'", k)
    return len(text) if end < 0 or end - i > 12 else end + 1


# Characters that can begin a comment, string, character literal or preprocessor line, or end a line.
_MASK_NEXT = re.compile(r"[\n#/\"'$@]")


def mask(text: str) -> str:
    """`text` with comments, strings, character literals and preprocessor lines blanked (newlines kept)."""
    text = text.replace("\ufeff", " ")                           # a byte-order mark is not code
    chars = list(text)
    n, i, line_start = len(text), 0, True
    while i < n:
        m = _MASK_NEXT.search(text, i)                         # jump to the next character that can start something
        if m is None:
            break
        j = m.start()
        if line_start and j > i and not text[i:j].isspace():
            line_start = False
        i, c = j, text[j]
        if c == "\n":
            line_start, i = True, i + 1
            continue
        if line_start and c == "#":
            end = text.find("\n", i)
            end = n if end < 0 else end
            _blank(chars, i, end)
            i = end
            continue
        if not c.isspace():
            line_start = False
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            _blank(chars, i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            _blank(chars, i, end)
            i = end
        elif c == '"' or (c in "$@" and i + 1 < n and text[i + 1] in '"$@'):
            end = _string_end(text, i)
            if end is None:
                i += 1
                continue
            _blank(chars, i, end)
            i = end
        elif c == "'":
            end = _char_end(text, i)
            _blank(chars, i, end)
            i = end
        else:
            i += 1
    return "".join(chars)


# ── headers ──────────────────────────────────────────────────────────────────

_ATTRS = re.compile(r"^\s*(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]\s*)+")
_ATTR_NAME = re.compile(r"(?:^|[\[,]\s*)(?:[A-Za-z_][\w.]*\.)?([A-Za-z_]\w*?)(?:Attribute)?\s*(?=[(\],])")
_TYPE_HEAD = re.compile(r"\b(class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+@?([A-Za-z_]\w*)")
_NS_HEAD = re.compile(r"^\s*namespace\s+([\w.]+)\s*$")


def _split_attrs(h: str) -> tuple[set[str], str]:
    m = _ATTRS.match(h)
    if not m:
        return set(), h
    names = set(_ATTR_NAME.findall(m.group(0)))
    return names, h[m.end():]


def _depth0(s: str, chars: str) -> list[int]:
    """Positions in `s` of any of `chars` outside (), [] and <> nesting."""
    out, par, ang = [], 0, 0
    for k, c in enumerate(s):
        if par == 0 and ang == 0 and c in chars:
            out.append(k)
        if c in "([":
            par += 1
        elif c in ")]":
            par -= 1
        elif c == "<" and s[k + 1:k + 2] not in "=<":
            ang += 1
        elif c == ">" and ang and s[k - 1:k] != "=":
            ang -= 1
    return out


def _arrow(h: str) -> int | None:
    """Index of a top-level `=>` in h, or None."""
    for k in _depth0(h, "="):
        if h[k + 1:k + 2] == ">":
            return k
    return None


def _assign(h: str) -> int | None:
    """Index of a top-level `=` that is an assignment (not `==`, `=>`, `<=`, `>=`, `!=`), or None."""
    for k in _depth0(h, "="):
        if h[k + 1:k + 2] in "=>" or h[k - 1:k] in "=!<>":
            continue
        return k
    return None


def _strip_generics(s: str) -> str:
    prev = None
    while prev != s:
        prev, s = s, re.sub(r"<[^<>]*>", "", s)
    return s


def _base_names(h: str) -> list[str]:
    """Simple names of the types a type header lists after `:` (generic arguments and `where` clauses dropped)."""
    h = re.split(r"\bwhere\b", h)[0]
    h = re.sub(r"\([^()]*\)", "", _strip_generics(h))
    if ":" not in h:
        return []
    return [p.strip().split(".")[-1] for p in h.split(":", 1)[1].split(",") if re.match(r"^\s*[A-Za-z_][\w.]*\s*$", p)]


_PARAM = re.compile(r"(?:^|,)\s*(?:\[[^\]]*\]\s*)?(?:(?:this|ref|out|in|params|scoped|readonly)\s+)*"
                    r"([A-Za-z_][\w.]*)\s*(?:<[^()]*?>)?\s*(?:\[\s*\])?\??\s+@?([A-Za-z_]\w*)")


def _params(p: str) -> dict[str, str]:
    """{parameter name: simple type name} for a parameter list's text."""
    p = re.sub(r"=[^,]*", "", _strip_generics(p))
    return {name: typ.split(".")[-1] for typ, name in _PARAM.findall(p)}


_ATTR_ANY = re.compile(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]")


def _top_parts(p: str) -> list[str]:
    """A parameter or argument list split at its top-level commas (outside (), [], {} and generic <>)."""
    parts, depth, cur = [], 0, []
    p = _strip_generics(p)
    for c in p:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return [x for x in parts if x.strip()]


def _arity(params: str, ext: bool) -> tuple[int, int | None]:
    """(required, maximum) arguments a parameter list accepts; maximum None with `params`; `this` not counted."""
    parts = _top_parts(params)
    if ext and parts:
        parts = parts[1:]
    varargs = any(re.match(r"\s*params\s", x) for x in parts)
    optional = sum(1 for x in parts if "=" in x and not re.match(r"\s*params\s", x))
    return len(parts) - optional - varargs, None if varargs else len(parts)


def _this_type(params: str) -> str | None:
    first = _top_parts(params)[:1]
    m = re.match(r"\s*this\s+(?:(?:ref|in|scoped|readonly)\s+)*([A-Za-z_][\w.]*)", first[0]) if first else None
    return m.group(1).split(".")[-1] if m else None


_ARG_SCAN = 4000                                                     # longer argument lists: count unknown


def _arg_count(body: str, raw: str, k: int) -> int | None:
    """Arguments of the call whose `(` is at body[k] (masked text; `raw` is the same span unmasked, for literals the
    mask blanked), or None when it cannot be counted for certain: no closing parenthesis within reach, or a `<` at
    the top level (a generic or a comparison: commas there are ambiguous)."""
    depth, commas, top_lt = 0, 0, False
    for j in range(k, min(len(body), k + _ARG_SCAN)):
        c = body[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                if top_lt:
                    return None
                inside = body[k + 1:j].strip() or any(q in raw[k + 1:j] for q in "\"'")
                return commas + 1 if inside else 0
        elif depth == 1:
            if c == ",":
                commas += 1
            elif c == "<":
                top_lt = True
    return None


def _member_head(h: str) -> dict | None:
    """Name, kind and parameter text of a member header (method, constructor, operator, property), or None."""
    h = re.sub(r"\s+", " ", h).strip()
    if not h or h.endswith("=>"):
        return None
    h = re.split(r"\bwhere\s+\w+\s*:", h)[0].strip()                 # generic constraints
    opens = [k for k in _depth0(h, "(")]
    # A tuple return type, `(int A, string B) Name(...)`, opens a parenthesis right after the modifiers: skip it.
    while len(opens) > 1 and not _MODIFIERS.sub("", _strip_generics(h[: opens[0]])).strip():
        opens = opens[1:]
    if opens:
        k = opens[0]
        close = _close(h, k)
        if close is None:
            return None
        before = _strip_generics(h[:k]).rstrip()
        if re.search(r"\boperator\s*\S+$", before) or re.search(r"\b(implicit|explicit)\s+operator\b", before):
            return {"name": "operator", "kind": "method", "params": h[k + 1:close], "static_ext": False}
        m = re.search(r"@?([A-Za-z_]\w*)$", before)
        if not m or m.group(1) in _NOT_CALL:
            return None
        rest = before[: m.start()].strip()
        if rest and not re.search(r"[\w>\]?)]$", rest) and rest[-1:] not in "~":
            return None
        params = h[k + 1:close]
        bare = _ATTR_ANY.sub(" ", params)                           # `[Attr] this Type x` is still an extension
        ext = bool(re.match(r"\s*this\s", bare)) and bool(re.search(r"\bstatic\b", h[:k]))
        gm = re.search(r"<([^<>]*)>\s*$", h[:k].rstrip())
        return {"name": m.group(1), "kind": "method", "params": params, "static_ext": ext, "ret": _ret_type(rest),
                "static": bool(re.search(r"\bstatic\b", h[:k])),
                "arity": _arity(bare, ext), "this_type": _this_type(bare) if ext else None,
                "gparams": {g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()} if gm else set()}
    if "[" in h and re.search(r"\bthis\s*\[", h):
        return {"name": "this[]", "kind": "method", "params": "", "static_ext": False}
    m = re.search(r"([A-Za-z_][\w.<>\[\],? ]*?)\s+@?([A-Za-z_]\w*)$", _strip_generics(h))
    if not m or m.group(2) in _NOT_CALL:
        return None
    return {"name": m.group(2), "kind": "property", "params": "", "static_ext": False, "ret": _ret_type(m.group(1))}


def _ret_type(rest: str) -> str | None:
    words = _MODIFIERS.sub(" ", rest).split()
    if not words:
        return None
    t = words[-1].rstrip("?").replace("[]", "")
    return t.split(".")[-1] if re.match(r"^[A-Za-z_][\w.]*$", t) else None


def _close(s: str, k: int) -> int | None:
    depth = 0
    for j in range(k, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return None


_FIELD = re.compile(r"(?:^|\s)([A-Za-z_][\w.]*)(?:<[^;=]*>)?\??(?:\[\])?\s+@?([A-Za-z_]\w*)\s*(?:=|$)")
_LOCAL_FN = re.compile(r"^(?:(?:static|async|unsafe|extern)\s+)*[A-Za-z_][\w.<>\[\],?\s]*?\s+@?([A-Za-z_]\w*)\s*"
                       r"(?:<[^()]*>)?\s*\(")


# ── pass 2: scan ─────────────────────────────────────────────────────────────

def scan_file(rel: str, text: str) -> dict:
    """{'symbols': [...], 'masked': str, 'nl': [...]} for one file."""
    masked = mask(text)
    nl = [k for k, c in enumerate(masked) if c == "\n"]

    def line(pos: int) -> int:
        return bisect_left(nl, pos) + 1

    symbols: list[dict] = []
    stack: list[dict] = [{"kind": "file", "q": ()}]
    file_ns: tuple[str, ...] = ()
    last = 0
    i, n = 0, len(masked)

    def ns_q() -> tuple[str, ...]:
        return stack[-1]["q"] if stack else ()

    def enclosing(kind: str) -> dict | None:
        for f in reversed(stack):
            if f["kind"] == kind:
                return f
        return None

    def add(kind: str, name: str, q: tuple[str, ...], start: int, end: int, **kw) -> dict:
        s = {"kind": kind, "name": name, "qparts": q, "line_start": line(start), "line_end": line(end), **kw}
        symbols.append(s)
        return s

    while i < n:
        c = masked[i]
        if c not in "{};":
            i += 1
            continue
        raw = masked[last:i]
        top = stack[-1]
        head_start = last + (len(raw) - len(raw.lstrip()))
        attrs, header = _split_attrs(raw)
        if c == "{":
            frame = {"kind": "block", "q": top["q"], "start": i}
            if top["kind"] in ("file", "ns"):
                nm = _NS_HEAD.match(header)
                tm = _TYPE_HEAD.search(header)
                if nm:
                    frame = {"kind": "ns", "q": top["q"] + tuple(nm.group(1).split("."))}
                elif tm:
                    frame = _type_frame(tm, header, top["q"], head_start, i, add, line)
            elif top["kind"] == "type":
                tm = _TYPE_HEAD.search(header)
                if tm and _assign(header) is None and "(" not in header[: tm.start()]:
                    frame = _type_frame(tm, header, top["q"], head_start, i, add, line)
                elif top.get("enum"):
                    frame = {"kind": "block", "q": top["q"], "start": i}
                elif _assign(header) is None and _arrow(header) is None:
                    mh = _member_head(header)
                    if mh:
                        frame = _member_frame(mh, attrs, header, top, head_start, i, add)
            elif top["kind"] == "member" and top.get("property"):
                frame = {"kind": "block", "q": top["q"], "start": i, "member": top["sym"]}   # an accessor body
            elif top["kind"] in ("member", "block"):
                owner = top.get("member") if top["kind"] == "block" else top["sym"]
                h = re.sub(r"\s+", " ", header).strip()
                first = h.split(" ", 1)[0].split("(")[0] if h else ""
                lm = _LOCAL_FN.match(h) if h and first not in _CONTROL and not h.endswith("=>") else None
                if lm and owner is not None and _assign(h) is None and lm.group(1) not in _NOT_CALL:
                    k = h.find("(", lm.end() - 1)
                    close = _close(h, k)
                    s = add("function", lm.group(1), owner["qparts"] + (lm.group(1),), head_start, i,
                            params=_params(h[k + 1:close] if close else ""), body=[], type_q=owner.get("type_q"),
                            attrs=set())
                    frame = {"kind": "member", "q": top["q"], "sym": s, "start": i}
                else:
                    frame = {"kind": "block", "q": top["q"], "start": i, "member": owner}
            stack.append(frame)
            last = i + 1
        elif c == "}":
            if len(stack) > 1:
                f = stack.pop()
                if f["kind"] == "member" and f.get("sym") is not None:
                    f["sym"]["body"].append((f["start"], i))
                    f["sym"]["line_end"] = line(i)
                elif f["kind"] == "type" and f.get("sym") is not None:
                    f["sym"]["line_end"] = line(i)
            last = i + 1
        else:  # ';'
            if top["kind"] in ("file", "ns"):
                nm = _NS_HEAD.match(header)
                if nm:                                             # file-scoped namespace: scope to end of file
                    file_ns = tuple(nm.group(1).split("."))
                    stack[-1] = {"kind": "ns", "q": stack[-1]["q"] + file_ns}
                else:
                    tm = _TYPE_HEAD.search(header)
                    if tm:                                         # `record R(int X);` with no body
                        _type_frame(tm, header, top["q"], head_start, i, add, line)
            elif top["kind"] == "type" and not top.get("enum"):
                arrow = _arrow(header)
                assign = _assign(header)
                if arrow is not None and (assign is None or assign > arrow):
                    mh = _member_head(header[:arrow])
                    if mh:
                        f = _member_frame(mh, attrs, header[:arrow], top, head_start, i, add)
                        f["sym"]["body"].append((last + arrow, i))
                elif "(" in header and assign is None:
                    mh = _member_head(header)                       # interface, abstract, extern or partial member
                    if mh:
                        _member_frame(mh, attrs, header, top, head_start, i, add)
                else:
                    fm = _FIELD.search(_MODIFIERS.sub(" ", header[:assign] if assign is not None else header))
                    if fm and fm.group(2) not in _NOT_CALL:
                        top["sym"]["fields"][fm.group(2)] = fm.group(1).split(".")[-1]
            elif top["kind"] == "member" and top.get("property"):
                pass                                                # `get; set;` or `get => x;`
            elif top["kind"] in ("member", "block"):
                owner = top.get("member") if top["kind"] == "block" else top["sym"]
                h = re.sub(r"\s+", " ", header).strip()
                arrow = _arrow(h)
                lm = _LOCAL_FN.match(h) if arrow is not None and _assign(h) is None else None
                if lm and owner is not None and lm.group(1) not in _NOT_CALL and h.split(" ", 1)[0] not in _CONTROL:
                    k = h.find("(", lm.end() - 1)
                    close = _close(h, k)
                    add("function", lm.group(1), owner["qparts"] + (lm.group(1),), head_start, i,
                        params=_params(h[k + 1:close] if close else ""), body=[(last, i)],
                        type_q=owner.get("type_q"), attrs=set())
            last = i + 1
        i += 1
    return {"symbols": symbols, "masked": masked, "nl": nl, "raw": text.replace("\ufeff", " ")}


def _type_frame(tm, header: str, q: tuple[str, ...], start: int, brace: int, add, line) -> dict:
    kind = "enum" if tm.group(1) == "enum" else "class"
    name = tm.group(2)
    tq = q + (name,)
    after = header[tm.end():]
    params = ""
    pm = re.match(r"\s*(?:<[^()]*?>)?\s*\(", after)                 # record or primary-constructor parameters
    if pm:
        k = after.find("(", 0)
        close = _close(after, k)
        params = after[k + 1:close] if close else ""
    sym = add(kind, name, tq, start, brace, bases=_base_names(after), fields=_params(params), type_q=tq,
              body=[], attrs=set(), is_interface=tm.group(1) == "interface")
    return {"kind": "type", "q": tq, "sym": sym, "enum": kind == "enum", "start": brace}


def _member_frame(mh: dict, attrs: set[str], header: str, top: dict, start: int, brace: int, add) -> dict:
    tsym = top["sym"]
    name = mh["name"]
    if name == tsym["name"] and mh["kind"] == "method":
        name = "ctor"
    s = add("method", name, top["q"] + (name,), start, brace, params=_params(mh["params"]), body=[],
            type_q=top["q"], attrs=attrs, ext=mh.get("static_ext", False), ret=mh.get("ret"),
            arity=mh.get("arity"), this_type=mh.get("this_type"), gparams=mh.get("gparams", set()),
            static=mh.get("static", False),
            is_test=bool(attrs & TEST_ATTRS))
    if mh["kind"] == "property" and mh.get("ret"):
        tsym["fields"][mh["name"]] = mh["ret"]
    return {"kind": "member", "q": top["q"], "sym": s, "start": brace, "property": mh["kind"] == "property"}


# ── call resolution ──────────────────────────────────────────────────────────

def generic_names(sym: dict) -> set[str]:
    """`this` types that accept any receiver: the method's generic parameters, and object."""
    return set(sym.get("gparams", ())) | {"object", "Object"}


class _Index:
    """Lookups that name exactly one symbol, or nothing."""

    def __init__(self, symbols: list[dict]) -> None:
        self.types: dict[str, list[dict]] = {}          # simple type name -> type symbols (partials included)
        self.members: dict[tuple[tuple[str, ...], str], list[dict]] = {}
        self.by_name: dict[str, list[dict]] = {}
        self.ext: dict[str, list[dict]] = {}            # extension methods by name
        self.ambiguous = False                          # set by member(): a member fits, but more than one
        # instance methods by name: on a receiver we cannot see, a call to such a name (with arguments it accepts)
        # may be that method, so an extension of the same name is not the only reading
        self.instance_methods: dict[str, list[dict]] = {}
        for s in symbols:
            if s["kind"] == "method" and not s.get("ext") and not s.get("static") and s.get("arity") is not None:
                # (no arity: a property, which `x.Name()` does not call)
                self.instance_methods.setdefault(s["name"], []).append(s)
        for s in symbols:
            if s["kind"] in ("class", "enum"):
                self.types.setdefault(s["name"], []).append(s)
            elif s["kind"] in ("method", "function"):
                self.by_name.setdefault(s["name"], []).append(s)
                if s["kind"] == "method":
                    self.members.setdefault((s["type_q"], s["name"]), []).append(s)
                if s.get("ext"):
                    self.ext.setdefault(s["name"], []).append(s)

    @staticmethod
    def _one(cands: list[dict]) -> dict | None:
        keys = {c["key"] for c in cands}
        return cands[0] if len(keys) == 1 else None

    def type_named(self, name: str, near: tuple[str, ...]) -> tuple[str, ...] | None:
        """The qualified name of the type `name` means from scope `near` (a type or a namespace): the innermost scope
        that declares it (a type nested in `near`, then each enclosing type and namespace outward), else the only type
        so named in the repository."""
        qs = {t["qparts"] for t in self.types.get(name, [])}
        for k in range(len(near), -1, -1):
            if near[:k] + (name,) in qs:
                return near[:k] + (name,)
        return next(iter(qs)) if len(qs) == 1 else None

    def bases(self, tq: tuple[str, ...]) -> list[str]:
        """Base names in declaration order (in C# the class base comes first), merged across partial declarations."""
        out: dict[str, None] = {}
        for t in self.types.get(tq[-1], []):
            if t["qparts"] == tq:
                out.update(dict.fromkeys(t.get("bases", [])))
        return list(out)

    @staticmethod
    def fits(sym: dict, n: int | None, explicit_this: bool = False) -> bool:
        """Whether `sym` accepts `n` arguments (unknown count or unknown arity: yes). `explicit_this`: the call names
        no receiver (`M(x)`, `Type.M(x)`), so an extension method's `this` is one of the `n`."""
        ar = sym.get("arity")
        if n is None or ar is None:
            return True
        if explicit_this and sym.get("ext"):
            n -= 1
        return ar[0] <= n and (ar[1] is None or n <= ar[1])

    def member(self, tq: tuple[str, ...], name: str, n: int | None = None, seen: frozenset = frozenset(),
               explicit_this: bool = False) -> dict | None:
        """The member `name` of type `tq` (or of its bases, class base first) that accepts `n` arguments. A type
        whose members of that name accept none of them hides nothing: the search goes on to its bases."""
        if tq in seen or len(seen) > 8:
            return None
        here = self.members.get((tq, name), [])
        fitting = [c for c in here if self.fits(c, n, explicit_this)]
        if fitting:
            one = self._one(fitting)
            if one is None:
                self.ambiguous = True                            # e.g. overloads split over partial-class files
            return one
        for b in self.bases(tq):
            bq = self.type_named(b, tq[:-1])
            if bq:
                found = self.member(bq, name, n, seen | {tq}, explicit_this)
                if found:
                    return found
        return None

    def ancestors(self, tq: tuple[str, ...]) -> set[str]:
        """Simple names of `tq` and every type it derives from or implements, as far as the repository shows."""
        out, todo, seen = {tq[-1]}, [tq], set()
        while todo and len(seen) < 2000:
            q = todo.pop()
            if q in seen:
                continue
            seen.add(q)
            for b in self.bases(q):
                out.add(b)
                bq = self.type_named(b, q[:-1])
                if bq:
                    todo.append(bq)
        return out

    def extension(self, name: str, n: int | None, rtype: str | None, near: tuple[str, ...]) -> dict | None:
        """The extension method `x.name(...)` means: among those so named that accept `n` arguments, the one whose
        `this` type fits the receiver. Receiver of a repository type: its own type, a base or an interface, or a
        generic parameter. Of an outside type (whose bases the repository cannot show): its name, `I` + its name
        (`ServiceCollection` → `IServiceCollection`) or a generic parameter. Unknown receiver: only when the name
        alone names one method, and it accepts the arguments.

        The argument count only ever rules candidates out; it never makes a choice. Narrowing several `Contains`
        extensions to the one taking one argument would send every `list.Contains(x)` to it (found on Jellyfin)."""
        every = self.ext.get(name, [])
        cands = [c for c in every if self.fits(c, n)]
        # `this T` (a generic parameter) and `this object` accept any receiver
        generic = [c for c in cands if c.get("this_type") in generic_names(c)]
        if rtype and rtype in self.types:
            # A repository type; when several share the name (Jellyfin: two `Series`), the call compiles against one
            # of them, so a candidate fitting any of their hierarchies is the only one that can be meant.
            rq = self.type_named(rtype, near)
            qs = [rq] if rq else sorted({t["qparts"] for t in self.types[rtype]})
            names = set().union(*(self.ancestors(q) for q in qs))
            return self._one([c for c in cands if c.get("this_type") in names] or generic)
        # an instance method of some repository type, so named and taking these arguments, could be the target
        shared = any(self.fits(c, n) for c in self.instance_methods.get(name, []))
        if rtype:
            # An outside type's own members are invisible here. Its exact name in `this` is safe; `this object` or
            # `this T` only when no repository type has an ordinary method of that name either (Polly:
            # `restClient.ExecuteAsync(request)` is RestSharp's, and `ResiliencePipeline.ExecuteAsync` exists).
            exact = [c for c in cands if c.get("this_type") in (rtype, "I" + rtype)]
            return self._one(exact or ([] if shared else generic))
        one = self._one(every)
        if one is None or n is None or shared:
            return None                       # unknown receiver: one method by that name, no ordinary method so named
        return one if any(self.fits(c, n) for c in every) else None

    def field_type(self, tq: tuple[str, ...], name: str) -> str | None:
        for t in self.types.get(tq[-1], []):
            if t["qparts"] == tq and name in t.get("fields", {}):
                return t["fields"][name]
        for b in self.bases(tq):
            bq = self.type_named(b, tq[:-1])
            if bq and bq != tq:
                found = self.field_type(bq, name)
                if found:
                    return found
        return None

    def constructor(self, name: str, near: tuple[str, ...], n: int | None = None) -> dict | None:
        tq = self.type_named(name, near)
        if not tq:
            return None
        return self._one([c for c in self.members.get((tq, "ctor"), []) if self.fits(c, n)]) or self._one(
            [t for t in self.types.get(tq[-1], []) if t["qparts"] == tq])


_CALL = re.compile(r"(?P<new>\bnew\s+)?(?P<chain>@?[A-Za-z_]\w*(?:\s*\??\.\s*@?[A-Za-z_]\w*)*)\s*"
                   r"(?:<[^<>();{}]*(?:<[^<>();{}]*>[^<>();{}]*)*>)?\s*\(")
_LOCAL = re.compile(r"(?:^|[;{(\s,])(?!(?:using|await|return|yield|throw|new|else|case|in|is|as|out|ref|const|"
                    r"static|readonly|fixed|unsafe|checked|lock|foreach|for|while|if|scoped)\s)"
                    r"(?:var|(?P<t>[A-Za-z_][\w.]*)(?:<[^;=(){}]*>)?\??(?:\[\])?)\s+@?(?P<n>[A-Za-z_]\w*)"
                    r"\s*(?:=\s*new\s+(?P<nt>[A-Za-z_][\w.]*))?")


def _locals(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _LOCAL.finditer(body):
        t = m.group("nt") or m.group("t")
        if t and t not in _NOT_CALL and m.group("n") not in _NOT_CALL:
            out.setdefault(m.group("n"), t.split(".")[-1])
    return out


# Only the text just before a call decides how to read it; slicing the whole body prefix per call was quadratic
# (a 1 MB generated method in EF Core did not finish in 5 minutes).
_LOOKBACK = 256

_KEEP_BEFORE = frozenset("return await yield throw new in is as case when else".split())


def _why(m, before: str, parts: list[str], rtype: str | None, name: str, index: "_Index") -> str:
    """Why a call to a name the repository defines got no edge (for `stats`; the graph does not store it)."""
    if m.group("new"):
        return "new-ambiguous-type"
    if before.endswith(".") or before.endswith(")"):
        return "chained"                                         # `a.B().C()`: the receiver is a call's result
    if len(parts) == 1:
        return "bare-not-in-type"                                # inherited from an outside base, or `using static`
    if len(index.ext.get(name, [])) > 1 and len({c["key"] for c in index.ext[name]}) > 1:
        return "extension-ambiguous"                             # several extension methods share the name
    if rtype:
        return "receiver-type-lacks-member"
    if len({c["key"] for c in index.by_name.get(name, [])}) > 1:
        return "receiver-unknown-ambiguous"                      # receiver's type unknown, several targets
    return "receiver-unknown-single"


def _calls_in(s: dict, masked: str, nl: list[int], index: _Index, locals_fns: dict[str, dict], raw: str = ""):
    """Yield (callee or None, confidence, line, text, why) for each call in `s`'s bodies; `why` is "resolved", or
    the reason it is not (see `_why`)."""
    tq = s.get("type_q") or ()
    nested = [span for f in locals_fns.values() for span in f.get("body", [])]   # a local function's calls are its own
    for start, end in s["body"]:
        body = masked[start:end]
        rbody = raw[start:end] if raw else body
        types = dict(s.get("params", {}))
        types.update(_locals(body))
        for m in _CALL.finditer(body):
            at = start + m.start()
            if any(a <= at < b for a, b in nested if not (a <= start and end <= b)):
                continue
            pre = body[max(0, m.start() - _LOOKBACK): m.start()].rstrip()
            word = re.search(r"([A-Za-z_]\w*)$", pre)
            if not m.group("new") and ((word and word.group(1) not in _KEEP_BEFORE and not pre.endswith("."))
                                       or (pre.endswith(">") and not pre.endswith("=>") and not pre.endswith("->"))):
                continue                                          # `T Name(...)`: a declaration, not a call
            chain = re.sub(r"\s+|\?", "", m.group("chain")).replace("@", "")
            parts = chain.split(".")
            name = parts[-1]
            if name in _NOT_CALL and not m.group("new"):
                continue
            before = body[max(0, m.start() - _LOOKBACK): m.start()].rstrip()
            line = bisect_left(nl, start + m.end("chain") - 1) + 1     # the name's line, not the chain's first
            found = None
            rtype = None
            index.ambiguous = False
            n = _arg_count(body, rbody, m.end() - 1)
            if m.group("new"):
                hit = index.constructor(name, tq, n)
                found = (hit, 0.6) if hit else None
            elif before.endswith("."):
                found = None                                     # a call on an expression's result: type unknown
            elif len(parts) == 1:
                hit = locals_fns.get(name) or (index.member(tq, name, n, explicit_this=True) if tq else None)
                found = (hit, 0.8) if hit else None
            else:
                if parts[0] == "this" and len(parts) > 2:
                    parts = parts[1:]                             # `this.field.M()` is `field.M()`
                recv, rest = parts[0], parts[1:-1]
                rtype = None
                if recv in ("this", "base") and not rest:
                    if recv == "this":
                        hit = index.member(tq, name, n) or index.extension(name, n, tq[-1] if tq else None, tq)
                    else:
                        hit = next((h for b in index.bases(tq) if (bq := index.type_named(b, tq))
                                    and (h := index.member(bq, name, n))), None)
                    found = (hit, 0.8) if hit else None
                else:
                    static = False
                    if not rest:
                        rtype = types.get(recv) or (index.field_type(tq, recv) if tq else None)
                        if rtype:
                            bq = index.type_named(rtype, tq)
                            hit = index.member(bq, name, n) if bq else None
                            found = (hit, 0.7) if hit else None
                        elif recv[:1].isupper() and (bq := index.type_named(recv, tq)):
                            static = True
                            hit = index.member(bq, name, n, explicit_this=True)   # `Type.Member(...)`: static
                            found = (hit, 0.7) if hit else None
                    elif rest and (bq := index.type_named(rest[-1], tq)) and rest[-1][:1].isupper():
                        static = True
                        hit = index.member(bq, name, n, explicit_this=True)       # `Ns.Type.Member(...)`
                        found = (hit, 0.6) if hit else None
                    if found is None and not index.ambiguous:      # `x.Ext()`: chosen by arguments and receiver;
                        # (C#: an instance member that fits wins over any extension, even when we cannot tell which)
                        # a failed `Type.M()` may be a property sharing a type's name (`User.GetUserId()`)
                        ext = index.extension(name, n, None if static else rtype, tq)
                        found = (ext, 0.6 if rtype else 0.5) if ext else None
            if found and found[0]["key"] == s["key"]:
                continue                                          # recursion: not an edge, not unresolved
            if found:
                yield found[0], found[1], line, chain, "resolved"
            elif name in index.by_name:
                yield None, 0.0, line, name, _why(m, before, parts, rtype if len(parts) > 1 else None, name, index)
            else:
                yield None, 0.0, line, name, "external"               # no symbol of that name in the repository


# ── repository ───────────────────────────────────────────────────────────────

def list_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.cs"], cwd=repo_root,
                          capture_output=True, text=True, check=False)
    return sorted(f for f in proc.stdout.splitlines() if f and not _SKIP.search(f))


def extract(repo_root: Path, stats: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(symbols, calls) for every tracked C# file. Symbols carry rel, key, qparts, kind, name, line_start, line_end;
    calls are {caller, callee, rel, line, text, confidence}, deduplicated per caller and callee."""
    scans: dict[str, dict] = {}
    for rel in list_files(repo_root):
        path = repo_root / rel
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        scans[rel] = scan_file(rel, text)
    symbols: list[dict] = []
    for rel, sc in scans.items():
        for s in sc["symbols"]:
            s["rel"] = rel
            s["key"] = f"{rel}::{'.'.join(s['qparts'])}"
            symbols.append(s)
    index = _Index(symbols)
    calls: dict[tuple[str, str], dict] = {}
    unresolved: dict[str, set[tuple[str, str]]] = {}
    local_fns: dict[tuple[str, ...], dict[str, dict]] = {}     # owner's qparts -> its local functions (one pass, not n²)
    for x in symbols:
        if x["kind"] == "function":
            local_fns.setdefault(x["qparts"][:-1], {})[x["name"]] = x
    for s in symbols:
        if not s.get("body"):
            continue
        sc = scans[s["rel"]]
        locals_fns = local_fns.get(s["qparts"], {})
        for callee, conf, line, text, why in _calls_in(s, sc["masked"], sc["nl"], index, locals_fns, sc["raw"]):
            if stats is not None:
                stats[why] = stats.get(why, 0) + 1
            if why == "external":
                continue
            if callee is None:
                unresolved.setdefault(text, set()).add((s["rel"], s["key"]))
                continue
            call = calls.setdefault((s["key"], callee["key"]), {
                "caller": s["key"], "callee": callee["key"], "rel": s["rel"], "line": line, "text": text,
                "confidence": conf})
            call["confidence"] = max(call["confidence"], conf)
    for s in symbols:
        if s["kind"] in ("method", "function") and s["name"] in unresolved:
            files: dict[str, int] = {}
            for rel, _caller in unresolved[s["name"]]:
                files[rel] = files.get(rel, 0) + 1
            s["unresolved_calls"] = sum(files.values())
            s["unresolved_files"] = sorted(files, key=lambda f: (-files[f], f))[:20]
            s["unresolved_file_count"] = len(files)
    return symbols, list(calls.values())


def tests_in_text(text: str) -> list[tuple[str, int]]:
    """[(test method name, line)] for methods carrying a test attribute (xUnit, NUnit, MSTest)."""
    sc = scan_file("", text)
    return sorted((s["name"], s["line_start"]) for s in sc["symbols"] if s.get("is_test"))


def add_to_graph(g, repo_root: Path) -> None:
    """Put the repository's C# symbols and calls into `g` (a DevKBGraph)."""
    symbols, calls = extract(repo_root)
    done: set[str] = set()
    for s in symbols:
        if s["key"] in done:
            continue
        done.add(s["key"])
        g.add_node("File", s["rel"], source="ast-csharp")
        g.add_node(
            "Symbol", s["key"], source="ast-csharp", kind=s["kind"], docstring_summary=None,
            decorators=sorted(s.get("attrs") or []), is_public=True, line_start=s["line_start"],
            line_end=s["line_end"],
            **{k: s[k] for k in ("unresolved_calls", "unresolved_files", "unresolved_file_count") if k in s},
        )
        g.add_edge("DEFINED_IN", "Symbol", s["key"], "File", s["rel"], source="ast-csharp", confidence=1.0,
                   evidence_ref=f"{s['rel']}:{s['line_start']}")
    for c in calls:
        g.add_edge(
            "CALLS", "Symbol", c["caller"], "Symbol", c["callee"], source="ast-csharp", confidence=c["confidence"],
            evidence_ref=f"{c['rel']}:{c['line']}: {c['caller'].split('::', 1)[1]} calls {c['text']}",
        )
