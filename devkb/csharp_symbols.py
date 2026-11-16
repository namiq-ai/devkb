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


def mask(text: str) -> str:
    """`text` with comments, strings, character literals and preprocessor lines blanked (newlines kept)."""
    text = text.replace("\ufeff", " ")                           # a byte-order mark is not code
    chars = list(text)
    n, i, line_start = len(text), 0, True
    while i < n:
        c = text[i]
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
        return {"name": m.group(1), "kind": "method", "params": params,
                "static_ext": bool(re.match(r"\s*this\s", params)) and bool(re.search(r"\bstatic\b", h[:k])),
                "ret": _ret_type(rest)}
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
    return {"symbols": symbols, "masked": masked, "nl": nl}


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
            is_test=bool(attrs & TEST_ATTRS))
    if mh["kind"] == "property" and mh.get("ret"):
        tsym["fields"][mh["name"]] = mh["ret"]
    return {"kind": "member", "q": top["q"], "sym": s, "start": brace, "property": mh["kind"] == "property"}


# ── call resolution ──────────────────────────────────────────────────────────

class _Index:
    """Lookups that name exactly one symbol, or nothing."""

    def __init__(self, symbols: list[dict]) -> None:
        self.types: dict[str, list[dict]] = {}          # simple type name -> type symbols (partials included)
        self.members: dict[tuple[tuple[str, ...], str], list[dict]] = {}
        self.by_name: dict[str, list[dict]] = {}
        self.ext: dict[str, list[dict]] = {}            # extension methods by name
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
        return sorted({b for t in self.types.get(tq[-1], []) if t["qparts"] == tq for b in t.get("bases", [])})

    def member(self, tq: tuple[str, ...], name: str, seen: frozenset = frozenset()) -> dict | None:
        if tq in seen or len(seen) > 8:
            return None
        hit = self._one(self.members.get((tq, name), []))
        if hit or self.members.get((tq, name)):
            return hit
        for b in self.bases(tq):
            bq = self.type_named(b, tq[:-1])
            if bq:
                found = self.member(bq, name, seen | {tq})
                if found:
                    return found
        return None

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

    def constructor(self, name: str, near: tuple[str, ...]) -> dict | None:
        tq = self.type_named(name, near)
        if not tq:
            return None
        return self._one(self.members.get((tq, "ctor"), [])) or self._one(
            [t for t in self.types.get(tq[-1], []) if t["qparts"] == tq])


_CALL = re.compile(r"(?P<new>\bnew\s+)?(?P<chain>@?[A-Za-z_]\w*(?:\s*\??\.\s*@?[A-Za-z_]\w*)*)\s*"
                   r"(?:<[^<>();{}]*(?:<[^<>();{}]*>[^<>();{}]*)*>)?\s*\(")
_LOCAL = re.compile(r"(?:^|[;{(\s,])(?:var|(?P<t>[A-Za-z_][\w.]*)(?:<[^;=(){}]*>)?\??(?:\[\])?)\s+@?(?P<n>[A-Za-z_]\w*)"
                    r"\s*(?:=\s*new\s+(?P<nt>[A-Za-z_][\w.]*))?")


def _locals(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _LOCAL.finditer(body):
        t = m.group("nt") or m.group("t")
        if t and t not in _NOT_CALL and m.group("n") not in _NOT_CALL:
            out.setdefault(m.group("n"), t.split(".")[-1])
    return out


_KEEP_BEFORE = frozenset("return await yield throw new in is as case when else".split())


def _calls_in(s: dict, masked: str, nl: list[int], index: _Index, locals_fns: dict[str, dict]):
    """Yield (callee or None, confidence, line, text) for each call in `s`'s bodies."""
    tq = s.get("type_q") or ()
    nested = [span for f in locals_fns.values() for span in f.get("body", [])]   # a local function's calls are its own
    for start, end in s["body"]:
        body = masked[start:end]
        types = dict(s.get("params", {}))
        types.update(_locals(body))
        for m in _CALL.finditer(body):
            at = start + m.start()
            if any(a <= at < b for a, b in nested if not (a <= start and end <= b)):
                continue
            pre = body[: m.start()].rstrip()
            word = re.search(r"([A-Za-z_]\w*)$", pre)
            if not m.group("new") and ((word and word.group(1) not in _KEEP_BEFORE and not pre.endswith("."))
                                       or (pre.endswith(">") and not pre.endswith("=>") and not pre.endswith("->"))):
                continue                                          # `T Name(...)`: a declaration, not a call
            chain = re.sub(r"\s+|\?", "", m.group("chain")).replace("@", "")
            parts = chain.split(".")
            name = parts[-1]
            if name in _NOT_CALL and not m.group("new"):
                continue
            before = body[: m.start()].rstrip()
            line = bisect_left(nl, start + m.end("chain") - 1) + 1     # the name's line, not the chain's first
            found = None
            if m.group("new"):
                hit = index.constructor(name, tq)
                found = (hit, 0.6) if hit else None
            elif before.endswith("."):
                found = None                                     # a call on an expression's result: type unknown
            elif len(parts) == 1:
                hit = locals_fns.get(name) or (index.member(tq, name) if tq else None)
                found = (hit, 0.8) if hit else None
            else:
                recv, rest = parts[0], parts[1:-1]
                rtype = None
                if recv in ("this", "base") and not rest:
                    if recv == "this":
                        hit = index.member(tq, name)
                    else:
                        hit = next((h for b in index.bases(tq) if (bq := index.type_named(b, tq))
                                    and (h := index.member(bq, name))), None)
                    found = (hit, 0.8) if hit else None
                else:
                    if not rest:
                        rtype = types.get(recv) or (index.field_type(tq, recv) if tq else None)
                        if rtype:
                            bq = index.type_named(rtype, tq)
                            hit = index.member(bq, name) if bq else None
                            found = (hit, 0.7) if hit else None
                        elif recv[:1].isupper() and (bq := index.type_named(recv, tq)):
                            hit = index.member(bq, name)          # `Type.Member(...)`: a static call
                            found = (hit, 0.7) if hit else None
                    elif rest and (bq := index.type_named(rest[-1], tq)) and rest[-1][:1].isupper():
                        hit = index.member(bq, name)              # `Ns.Type.Member(...)`
                        found = (hit, 0.6) if hit else None
                    if found is None and (not rtype or index.type_named(rtype, tq) is None):
                        ext = index._one(index.ext.get(name, []))   # receiver of an unknown or external type
                        found = (ext, 0.5) if ext else None       # `x.Ext()`: the only extension method so named
            if found and found[0]["key"] == s["key"]:
                continue                                          # recursion: not an edge, not unresolved
            if found:
                yield found[0], found[1], line, chain
            elif name in index.by_name:
                yield None, 0.0, line, name


# ── repository ───────────────────────────────────────────────────────────────

def list_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.cs"], cwd=repo_root,
                          capture_output=True, text=True, check=False)
    return sorted(f for f in proc.stdout.splitlines() if f and not _SKIP.search(f))


def extract(repo_root: Path) -> tuple[list[dict], list[dict]]:
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
    for s in symbols:
        if not s.get("body"):
            continue
        sc = scans[s["rel"]]
        locals_fns = {x["name"]: x for x in symbols if x["kind"] == "function" and x["qparts"][:-1] == s["qparts"]}
        for callee, conf, line, text in _calls_in(s, sc["masked"], sc["nl"], index, locals_fns):
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
