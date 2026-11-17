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

from devkb import csharp_dotnet as dotnet

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
    # raw string: N quotes ... N quotes. Never verbatim: `@""""` is a verbatim string holding one quote (#57)
    if not verbatim and text.startswith('"""', k):
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
_ATTR_NAME = re.compile(r"(?:^|[\[,]\s*)(?:[^\W\d][\w.]*\.)?([^\W\d]\w*?)(?:Attribute)?\s*(?=[(\],])")
_TYPE_HEAD = re.compile(r"\b(class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+@?([^\W\d]\w*)")
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


def _base_types(h: str) -> list[tuple]:
    """The types a type header lists after `:`, with their generic arguments (`AbstractValidator<Person>`)."""
    h = re.split(r"\bwhere\b", h)[0]
    h = re.sub(r"^\s*<[^<>]*(?:<[^<>]*>[^<>]*)*>", "", h)            # the type's own parameter list
    h = re.sub(r"^\s*\([^()]*(?:\([^()]*\)[^()]*)*\)", "", h)          # a record's or primary constructor's parameters
    k = h.find(":")
    if k < 0:
        return []
    out = []
    for part in _split_top(h[k + 1:]):
        part = re.sub(r"\([^()]*(?:\([^()]*\)[^()]*)*\)\s*$", "", part.strip())   # `Base(args)`: the base call
        t = _pt(part)
        if t:
            out.append(t)
    return out


def _subst(t, binding: dict):
    """`t` with generic parameter names replaced by what `binding` maps them to (F1)."""
    if not t or not binding:
        return t
    if not t[1] and t[0] in binding:
        return binding[t[0]]
    return (t[0], tuple(_subst(x, binding) for x in t[1]))


def _unify(pt, at, gps: set, out: dict) -> None:
    """Bind the method's generic parameters `gps` by matching parameter type `pt` against argument type `at`."""
    if not pt or not at:
        return
    if pt[0] in gps and not pt[1]:
        out.setdefault(pt[0], at)
        return
    if pt[1] and at[1] and len(pt[1]) == len(at[1]) and (pt[0] == at[0] or pt[0] in dotnet.ancestors(at[0])):
        for p_, a__ in zip(pt[1], at[1]):
            _unify(p_, a__, gps, out)
    elif pt[1] and len(pt[1]) == 1 and at[0] == "Array" and at[1] and pt[0] in dotnet.ancestors("Array"):
        _unify(pt[1][0], at[1][0], gps, out)           # T[] passed as IEnumerable<T>


def _base_names(h: str) -> list[str]:
    """Simple names of the types a type header lists after `:` (generic arguments and `where` clauses dropped)."""
    h = re.split(r"\bwhere\b", h)[0]
    h = re.sub(r"\([^()]*\)", "", _strip_generics(h))
    if ":" not in h:
        return []
    return [p.strip().split(".")[-1] for p in h.split(":", 1)[1].split(",") if re.match(r"^\s*[^\W\d][\w.]*\s*$", p)]


_PARAM = re.compile(r"(?:^|,)\s*(?:\[[^\]]*\]\s*)?(?:(?:this|ref|out|in|params|scoped|readonly)\s+)*"
                    r"([^\W\d][\w.]*)\s*(?:<[^()]*?>)?\s*(?:\[\s*\])?\??\s+@?([^\W\d]\w*)")


def _params(p: str) -> dict[str, str]:
    """{parameter name: simple type name} for a parameter list's text."""
    p = re.sub(r"=[^,]*", "", _strip_generics(p))
    return {name: typ.split(".")[-1] for typ, name in _PARAM.findall(p)}


_ATTR_ANY = re.compile(r"\[\s*[^\W\d][^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]")   # an attribute starts with a name; `[]` is an array


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
    m = re.match(r"\s*this\s+(?:(?:ref|in|scoped|readonly)\s+)*([^\W\d][\w.]*)", first[0]) if first else None
    return m.group(1).split(".")[-1] if m else None


def _split_top(s: str, sep: str = ",") -> list[str]:
    """`s` split at `sep` outside (), [], {} and generic <>; generic text is kept."""
    parts, depth, cur = [], 0, []
    for c in s:
        if c in "<([{":
            depth += 1
        elif c in ">)]}" and depth:
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return [x for x in parts if x.strip()]


def _strip_end_generics(s: str) -> str:
    """`s` without a balanced `<...>` at its end (a method's own generic parameter list)."""
    s = s.rstrip()
    if not s.endswith(">"):
        return s
    depth = 0
    for j in range(len(s) - 1, -1, -1):
        if s[j] == ">":
            depth += 1
        elif s[j] == "<":
            depth -= 1
            if depth == 0:
                return s[:j].rstrip()
    return s


def _pt(text: str | None):
    """A type's text as (simple name, (argument types...)); arrays are ("Array", (element,)). None if not a type."""
    t = re.sub(r"\s+", "", text or "").replace("?", "").replace("global::", "")
    if not t or t.startswith("("):
        return None
    arr = 0
    while t.endswith("[]"):
        t, arr = t[:-2], arr + 1
    m = re.match(r"^([^\W\d][\w.]*)(?:<(.*)>)?$", t)
    if m:
        args = tuple(_pt(a) for a in _split_top(m.group(2))) if m.group(2) else ()
        out = (m.group(1).split(".")[-1], args)
    else:
        mm = re.match(r"^([^\W\d][\w.]*)", t)                 # unbalanced generics: the outer name is enough
        if not mm:
            return None
        out = (mm.group(1).split(".")[-1], ())
    for _ in range(arr):
        out = ("Array", (out,))
    return out


def _last_type_token(text: str):
    """The type at the end of `text` once attributes and modifiers are gone (a return or property type)."""
    text = _MODIFIERS.sub(" ", _ATTR_ANY.sub(" ", text))
    toks = _split_top(text.strip(), " ")
    return _pt(toks[-1]) if toks else None


def _pfull(params: str) -> list[dict]:
    """Each parameter: name, parsed type, whether optional, whether `params`, whether `this`."""
    out = []
    for part in _split_top(_ATTR_ANY.sub(" ", params)):
        decl = _split_top(part, "=")[0] if "=" in part else part
        optional = "=" in part and not part.strip().startswith("=")
        mods = re.match(r"\s*((?:(?:this|ref|out|in|params|scoped|readonly)\s+)*)", decl)
        words = mods.group(1).split()
        toks = _split_top(decl[mods.end():].strip(), " ")
        if len(toks) < 2:
            continue
        out.append({"name": toks[-1].lstrip("@"), "t": _pt("".join(toks[:-1])), "optional": optional,
                    "params": "params" in words, "this": "this" in words})
    return out


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


class _Args:
    """A call's arguments: `n` (None when uncertain), per-argument text and span, their types where certain, and
    whether any is named (which switches the type check off: positions no longer map to parameters)."""
    __slots__ = ("n", "items", "close", "named", "types")

    def __init__(self, n, items, close, named):
        self.n, self.items, self.close, self.named, self.types = n, items, close, named, None


def _args(body: str, raw: str, k: int) -> _Args:
    """The arguments of the call whose `(` is at body[k] (same rules as `_arg_count`)."""
    depth, cuts, top_lt = 0, [k], False
    for j in range(k, min(len(body), k + _ARG_SCAN)):
        c = body[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                if not (body[k + 1:j].strip() or any(q in raw[k + 1:j] for q in "\"'")):
                    return _Args(0, [], j, False)
                cuts.append(j)
                if top_lt:
                    return _Args(None, None, j, False)
                items = [(body[a + 1:b], raw[a + 1:b], a + 1, b) for a, b in zip(cuts, cuts[1:])]
                named = any(re.match(r"\s*@?[^\W\d]\w*\s*:(?!:)", it[0]) for it in items)
                return _Args(len(items), items, j, named)
        elif depth == 1:
            if c == ",":
                cuts.append(j)
            elif c == "<":
                top_lt = True
    return _Args(None, None, None, False)


_LAMBDA = re.compile(r"^\s*(?:static\s+)?(?:async\s+)?(?:\(\s*(?P<ps>[^()]*)\)|@?(?P<p>[^\W\d]\w*))\s*=>")


def _arg_type(mtext: str, rtext: str, type_of):
    """An argument's type where its text makes it certain, else None. `type_of(name)` types an identifier."""
    mt, rt = mtext.strip(), rtext.strip()
    if not rt:
        return None
    if not mt and rt[:1] in "\"$@":
        return ("string", ())                                    # a whole string literal (the mask blanks it)
    if not mt and rt[:1] == "'":
        return ("char", ())
    if re.match(r"^nameof\s*\(", mt) and mt.endswith(")"):
        return ("string", ())
    if re.match(r"^-?\d[\d_]*(?:\.\d+)?[fFdDmMuUlL]*$", mt):
        return ("#number", ())
    if mt in ("true", "false"):
        return ("bool", ())
    if _LAMBDA.match(mt):
        return ("#lambda", ())
    m = re.match(r"^new\s+([^\W\d][\w.]*(?:<[^()]*>)?)\s*(?:\([^()]*\)|\{[^{}]*\})$", mt)
    if m:
        return _pt(m.group(1))
    m = re.match(r"^@?([^\W\d]\w*)$", mt)
    if m and m.group(1) not in ("null", "default", "this", "base"):
        return type_of(m.group(1))
    return None


def _lambda_param_types(pt, k: int):
    """The parameter types a lambda with `k` parameters gets when passed where `pt` (a parsed type) is expected."""
    if pt and pt[0] == "Expression" and pt[1]:
        pt = pt[1][0]
    if not pt:
        return None
    if pt[0] == "Func":
        ts = list(pt[1][:-1])
    elif pt[0] in ("Action", "Predicate"):
        ts = list(pt[1])
    else:
        return None
    return ts if len(ts) == k else None


def _unwrap(t):
    """`await x` where x is a `t`: a Task's or ValueTask's result type."""
    if t and t[0] in dotnet.AWAITABLE:
        return t[1][0] if t[1] else None
    return t


def _elem(t):
    """The element type of a `foreach` over a `t`."""
    if not t:
        return None
    if t[0] == "Array" or (t[0] in dotnet.SEQUENCES and t[1]):
        return t[1][0] if t[1] else None
    return None


def _local_fn_sig(h: str, k: int, ptext: str) -> dict:
    """A local function's signature, as `_member_head` records a method's: arity, parameter and return types."""
    bare = _ATTR_ANY.sub(" ", ptext)
    head = re.sub(r"@?[^\W\d]\w*$", "", _strip_end_generics(h[:k]))
    head = re.sub(r"\b(static|async|unsafe|extern)\b", " ", head)
    gm = re.search(r"<([^<>]*)>\s*$", h[:k].rstrip())
    glist = [g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()] if gm else []
    return {"arity": _arity(bare, False), "pfull": _pfull(ptext), "ret_full": _last_type_token(head),
            "gparams": set(glist), "gparams_list": glist}


_MODIFIER_WORDS = frozenset("public private protected internal static readonly sealed abstract virtual override "
                            "async unsafe extern new partial volatile required file const".split())


_WHERE = re.compile(r"\bwhere\s+@?([^\W\d]\w*)\s*:\s*([^\W\d][\w.]*)")


def _constraints(h: str) -> dict[str, str]:
    """{T: its first constraint's simple name} from `where T : Base, new()` clauses (class/struct/new() skipped)."""
    out = {}
    for t, c in _WHERE.findall(h):
        c = c.split(".")[-1]
        if c not in ("class", "struct", "new", "unmanaged", "notnull", "default", "allows"):
            out.setdefault(t, c)
    return out


def _index_elem(t):
    """The type of `x[i]` for an `x` of type `t` (F7): arrays, lists, read-only lists, collections, spans; a
    dictionary's value; a string's char. None when the indexer is not one of these."""
    if not t:
        return None
    if t[0] == "Array" or (t[0] in ("List", "IList", "IReadOnlyList", "Collection", "ReadOnlyCollection",
                                     "ImmutableArray", "ImmutableList", "Span", "ReadOnlySpan", "Memory",
                                     "ReadOnlyMemory", "ObservableCollection") and t[1]):
        return t[1][0] if t[1] else None
    if t[0] in ("Dictionary", "IDictionary", "IReadOnlyDictionary", "ConcurrentDictionary", "SortedDictionary",
                "ImmutableDictionary") and len(t[1]) == 2:
        return t[1][1]
    if t[0] in ("string", "String"):
        return ("char", ())
    return None


def _open_of(body: str, q: int) -> int | None:
    """Index of the bracket that opens the one closing at body[q] (`)`, `]` or `}`), scanning back a bounded span."""
    pairs = {")": "(", "]": "[", "}": "{"}
    depth, j, lo = 0, q, max(0, q - _ARG_SCAN)
    while j >= lo:
        c = body[j]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            depth -= 1
            if depth == 0:
                return j if body[j] == pairs[body[q]] else None
        j -= 1
    return None


_CAST = re.compile(r"^\s*\(\s*([^\W\d][\w.]*(?:<[^()]*>)?(?:\[\])?\??)\s*\)\s*[\w@(]")
_AS = re.compile(r"\bas\s+([^\W\d][\w.]*(?:<[^()]*>)?)\s*$")
_GENERIC_TYPE_END = re.compile(r"(?<![\w.])([^\W\d][\w.]*)\s*<([^<>()]*(?:<[^<>()]*>[^<>()]*)*)>$")
# declarations whose type the source writes (F8): `var x = (T)y;`, `var x = y as T;`, `y is T x`, `case T x`
_DECL_CAST = re.compile(r"\bvar\s+@?([^\W\d]\w*)\s*=\s*\(\s*([^\W\d][\w.]*(?:<[^()]*>)?(?:\s*\[\s*\])*)\s*\)\s*[\w@(]")
_DECL_AS = re.compile(r"\bvar\s+@?([^\W\d]\w*)\s*=\s*[^;=]*?\bas\s+([^\W\d][\w.]*(?:<[^;()]*?>)?)\s*;")
_DECL_PATTERN = re.compile(r"\b(?:is|case)\s+(?:not\s+)?([^\W\d][\w.]*(?:<[^()]*?>)?)\s+@?([^\W\d]\w*)\b"
                           r"(?!\s*[(<.])"
                           # a switch-expression arm: `ArrayConstantExpression e => ...` (EF Core), `T e when c => ...`
                           r"|(?:^|[{,(]\s*)([A-Z][\w.]*(?:<[^()]*?>)?)\s+@?([a-z_]\w*)\s*(?:when\b[^=]*)?=>", re.M)


def _member_head(h: str) -> dict | None:
    """Name, kind and parameter text of a member header (method, constructor, operator, property), or None."""
    h = re.sub(r"\s+", " ", h).strip()
    if not h or h.endswith("=>"):
        return None
    gcons = _constraints(h)
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
        m = re.search(r"@?([^\W\d]\w*)$", before)
        if not m or m.group(1) in _NOT_CALL or m.group(1) in _MODIFIER_WORDS:
            return None                       # `private (int A, string B) _field;`: a tuple type, not a method `private`
        rest = before[: m.start()].strip()
        name, ret_text = m.group(1), re.sub(r"@?[^\W\d]\w*$", "", _strip_end_generics(h[:k]))
        qm = _EXPLICIT_IFACE.search(rest)
        if qm and rest[: qm.start(1)].strip():
            # `void IRunner.Run()`: an explicit interface implementation, keyed with its interface's name so it
            # stays apart from a `Run()` of the type's own, which a call by simple name means (#79)
            name, rest, ret_text = f"{qm.group(2)}.{name}", rest[: qm.start(1)].strip(), _drop_qualifier(ret_text)
        if rest and not re.search(r"[\w>\]?)]$", rest) and rest[-1:] not in "~":
            return None
        params = h[k + 1:close]
        bare = _ATTR_ANY.sub(" ", params)                           # `[Attr] this Type x` is still an extension
        ext = bool(re.match(r"\s*this\s", bare)) and bool(re.search(r"\bstatic\b", h[:k]))
        gm = re.search(r"<([^<>]*)>\s*$", h[:k].rstrip())
        glist = [g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()] if gm else []
        return {"name": name, "kind": "method", "params": params, "static_ext": ext, "ret": _ret_type(rest),
                "ret_full": _last_type_token(ret_text) if rest else None, "pfull": _pfull(params), "gcons": gcons,
                "gparams_list": glist,
                "static": bool(re.search(r"\bstatic\b", h[:k])),
                "arity": _arity(bare, ext), "this_type": _this_type(bare) if ext else None,
                "gparams": {g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()} if gm else set()}
    if "[" in h and re.search(r"\bthis\s*\[", h):
        return {"name": "this[]", "kind": "method", "params": "", "static_ext": False}
    em = re.search(r"^(.*\S)\s+((?:[^\W\d]\w*\.)*(I[A-Z]\w*))\.@?([^\W\d]\w*)$", _strip_generics(h))
    if em and re.search(r"[\w>\]?)]$", em.group(1)):                # `int IRunner.Count { get ... }` (#79)
        return {"name": f"{em.group(3)}.{em.group(4)}", "kind": "property", "params": "", "static_ext": False,
                "ret": _ret_type(em.group(1)), "ret_full": _last_type_token(_drop_qualifier(
                    re.sub(r"\s*@?[^\W\d]\w*$", "", h)))}
    m = re.search(r"([^\W\d][\w.<>\[\],? ]*?)\s+@?([^\W\d]\w*)$", _strip_generics(h))
    if not m or m.group(2) in _NOT_CALL:
        return None
    return {"name": m.group(2), "kind": "property", "params": "", "static_ext": False, "ret": _ret_type(m.group(1)),
            "ret_full": _last_type_token(re.sub(r"\s*@?[^\W\d]\w*$", "", h))}


# the interface an explicit implementation names before its member: `IRunner.`, `System.IDisposable.` (generics gone)
_EXPLICIT_IFACE = re.compile(r"(?:^|\s)((?:[^\W\d]\w*\.)*(I[A-Z]\w*))\.$")


def _drop_qualifier(s: str) -> str:
    """`s` (a header up to a member's name) without the `IName<...>.` that ends it."""
    s = s.rstrip()
    if s.endswith("."):
        s = re.sub(r"[\w.]*$", "", _strip_end_generics(s[:-1]))
    return s


def _ret_type(rest: str) -> str | None:
    words = _MODIFIERS.sub(" ", rest).split()
    if not words:
        return None
    t = words[-1].rstrip("?").replace("[]", "")
    return t.split(".")[-1] if re.match(r"^[^\W\d][\w.]*$", t) else None


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


_FIELD = re.compile(r"(?:^|\s)(?P<t>[^\W\d][\w.]*(?:<[^;=]*>)?)\??(?P<arr>\[\])?\s+@?(?P<n>[^\W\d]\w*)\s*(?:=|$)")
_LOCAL_FN = re.compile(r"^(?:(?:static|async|unsafe|extern)\s+)*[^\W\d][\w.<>\[\],?\s]*?\s+@?([^\W\d]\w*)\s*"
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
        if c == "{" and top["kind"] in ("file", "ns", "type") and raw.count("[") > raw.count("]"):
            # `[InlineData(new int[] { 1, 2 }, 3)]`: a brace inside an open attribute is part of its argument, not a
            # scope; its `}` and any `;` inside it belong to the header too (#78)
            depth, close = 0, None
            for j in range(i, n):
                if masked[j] == "{":
                    depth += 1
                elif masked[j] == "}":
                    depth -= 1
                    if depth == 0:
                        close = j
                        break
            if close is not None:                # never closed: read as before (and no rescan per later `{`)
                i = close + 1
                continue
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
                elif (arrow := _arrow(header)) is not None and not top.get("pending") and \
                        (_assign(header) is None or _assign(header) > arrow):
                    # `... => new X { A = 1 };` or `=> Run(x => { ... });`: an expression-bodied member whose
                    # expression holds braces. Its body runs from the arrow to the `;` that ends it at type level.
                    mh = _member_head(header[:arrow])
                    if mh:
                        f = _member_frame(mh, attrs, header[:arrow], top, head_start, i, add)
                        top["pending"] = (f["sym"], last + arrow)
                        frame = {"kind": "block", "q": top["q"], "start": i, "member": f["sym"]}
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
                    ptext = h[k + 1:close] if close else ""
                    s = add("function", lm.group(1), owner["qparts"] + (lm.group(1),), head_start, i,
                            params=_params(ptext), body=[], type_q=owner.get("type_q"), attrs=set(),
                            **_local_fn_sig(h, k, ptext))
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
            elif top["kind"] == "type" and top.get("pending"):
                sym, body_start = top.pop("pending")             # the end of a braced expression body
                sym["body"].append((body_start, i))
                sym["line_end"] = line(i)
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
                    if fm and fm.group("n") not in _NOT_CALL:
                        top["sym"]["fields"][fm.group("n")] = re.sub(r"<.*", "", fm.group("t")).split(".")[-1]
                        ft = _pt(fm.group("t") + (fm.group("arr") or ""))
                        if ft:
                            top["sym"].setdefault("ffull", {})[fm.group("n")] = ft
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
                    ptext = h[k + 1:close] if close else ""
                    add("function", lm.group(1), owner["qparts"] + (lm.group(1),), head_start, i,
                        params=_params(ptext), body=[(last, i)],
                        type_q=owner.get("type_q"), attrs=set(), **_local_fn_sig(h, k, ptext))
            last = i + 1
        i += 1
    aliases = {m.group(1): t for m in _ALIAS.finditer(masked) if (t := _pt(m.group(2)))}
    if aliases:
        for sym in symbols:
            _dealias_symbol(sym, aliases)
    return {"symbols": symbols, "masked": masked, "nl": nl, "raw": text.replace("\ufeff", " "), "aliases": aliases}


# `using BaseItemDto = MediaBrowser.Controller.Entities.BaseItem;` (Jellyfin): the alias names another type
_ALIAS = re.compile(r"^[ \t]*(?:global\s+)?using\s+@?([^\W\d]\w*)\s*=\s*([^;=]+);", re.M)


def _dealias(t, aliases: dict):
    if not t or not aliases:
        return t
    target = aliases.get(t[0])
    args = tuple(_dealias(x, aliases) for x in t[1])
    if target is None:
        return (t[0], args)
    return (target[0], args or target[1])


def _dealias_symbol(sym: dict, aliases: dict) -> None:
    """Rewrite every type a symbol records through its file's `using X = Y;` aliases."""
    name = lambda n: aliases[n][0] if n in aliases else n           # noqa: E731
    for p in sym.get("pfull") or []:
        p["t"] = _dealias(p["t"], aliases)
    if sym.get("ret_full"):
        sym["ret_full"] = _dealias(sym["ret_full"], aliases)
    if sym.get("ret"):
        sym["ret"] = name(sym["ret"])
    if sym.get("this_type"):
        sym["this_type"] = name(sym["this_type"])
    for d in ("params", "fields"):
        if sym.get(d):
            sym[d] = {k: name(v) for k, v in sym[d].items()}
    if sym.get("ffull"):
        sym["ffull"] = {k: _dealias(v, aliases) for k, v in sym["ffull"].items()}
    if sym.get("bases"):
        sym["bases"] = [name(b) for b in sym["bases"]]
    if sym.get("bases_full"):
        sym["bases_full"] = [_dealias(b, aliases) for b in sym["bases_full"]]


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
    gm = re.match(r"\s*<([^<>]*)>", after)
    tg_list = [g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()] if gm else []
    sym = add(kind, name, tq, start, brace, bases=_base_names(after), fields=_params(params), type_q=tq,
              tgparams_list=tg_list, bases_full=_base_types(after),
              body=[], attrs=set(), is_interface=tm.group(1) == "interface",
              ffull={p["name"]: p["t"] for p in _pfull(params) if p["t"]},
              tgparams={g.strip().split()[-1] for g in gm.group(1).split(",") if g.strip()} if gm else set(),
              tgcons=_constraints(after))
    return {"kind": "type", "q": tq, "sym": sym, "enum": kind == "enum", "start": brace}


def _member_frame(mh: dict, attrs: set[str], header: str, top: dict, start: int, brace: int, add) -> dict:
    tsym = top["sym"]
    name = mh["name"]
    if name == tsym["name"] and mh["kind"] == "method":
        name = "ctor"
    s = add("method", name, top["q"] + (name,), start, brace, params=_params(mh["params"]), body=[],
            type_q=top["q"], attrs=attrs, ext=mh.get("static_ext", False), ret=mh.get("ret"),
            arity=mh.get("arity"), this_type=mh.get("this_type"), gparams=mh.get("gparams", set()),
            static=mh.get("static", False), ret_full=mh.get("ret_full"), pfull=mh.get("pfull"),
            gcons=mh.get("gcons") or {}, gparams_list=mh.get("gparams_list") or [],
            is_test=bool(attrs & TEST_ATTRS))
    if mh["kind"] == "property" and mh.get("ret") and "." not in mh["name"]:
        tsym["fields"][mh["name"]] = mh["ret"]
        if mh.get("ret_full"):
            tsym.setdefault("ffull", {})[mh["name"]] = mh["ret_full"]
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
        self.by_key: dict[str, list[dict]] = {}        # overloads share a key
        self.type_gparams: dict[tuple, set[str]] = {}
        self.type_cons: dict[tuple, dict[str, str]] = {}    # a type's generic parameters' constraints
        self._type_view: dict[tuple, dict | None] = {}      # type_sym(): partial declarations merged
        self.implicit: set[str] = set()                 # types declaring a conversion operator (any argument may fit)
        self.enums: set[str] = set()
        self._several: dict[tuple[str, str], bool] = {}
        for s in symbols:
            self.by_key.setdefault(s["key"], []).append(s)
            if s["kind"] in ("class", "enum"):
                self.type_gparams.setdefault(s["qparts"], set()).update(s.get("tgparams") or ())
                self.type_cons.setdefault(s["qparts"], {}).update(s.get("tgcons") or {})
                if s["kind"] == "enum":
                    self.enums.add(s["name"])
            if s["name"] == "operator" and s.get("type_q"):
                self.implicit.add(s["type_q"][-1])
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

    def several(self, table: str, name: str) -> bool:
        """Whether more than one key is named `name` in `table` ("by_name" or "ext"). Cached: a set built per call
        site was (definitions x call sites) on a repository with many same-named methods (#60)."""
        k = (table, name)
        if k not in self._several:
            self._several[k] = len({c["key"] for c in getattr(self, table).get(name, [])}) > 1
        return self._several[k]

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

    def fits(self, sym: dict, a, explicit_this: bool = False) -> bool:
        """Whether `sym` accepts the call's arguments `a` (an `_Args`, a count, or None): their number (round 2) and,
        where both sides are certain, their types (round 3). Unknown means yes. `explicit_this`: the call names no
        receiver (`M(x)`, `Type.M(x)`), so an extension method's `this` is one of the arguments."""
        n = a.n if isinstance(a, _Args) else a
        ar = sym.get("arity")
        if n is not None and ar is not None:
            m = n - 1 if explicit_this and sym.get("ext") else n
            if not (ar[0] <= m and (ar[1] is None or m <= ar[1])):
                return False
        return not isinstance(a, _Args) or self.accepts(sym, a, explicit_this)

    def _score(self, sym: dict, a, explicit_this: bool, rtype: str | None):
        """Per certain argument (and an extension's receiver): 3 identity, 2 a conversion to a specific type, 1 a
        generic parameter or object. None when a position cannot be scored."""
        ps = sym.get("pfull")
        if not ps or not isinstance(a, _Args) or a.types is None or a.named:
            return None
        gp = set(sym.get("gparams") or ()) | self.type_gparams.get(sym.get("type_q"), set())
        out = []
        if sym.get("ext") and not explicit_this:
            th = sym.get("this_type")
            out.append(1 if th in generic_names(sym) else 3 if th == rtype else 2)
            ps = ps[1:]
        for i, at in enumerate(a.types):
            if at is None or i >= len(ps) or not ps[i]["t"]:
                continue
            pt = ps[i]["t"]
            out.append(1 if pt[0] in gp or pt[0] in ("object", "Object") else 3 if pt[0] == at[0] else 2)
        return out

    def better(self, cands: list[dict], a, explicit_this: bool = False, rtype: str | None = None) -> dict | None:
        """F2: the one candidate (by key) at least as good as every other on every scored position and strictly
        better on one, by C#'s better-conversion rules as far as certain types decide them; else None."""
        by_key: dict[str, dict] = {}
        for c in cands:
            by_key.setdefault(c["key"], c)
        if len(by_key) < 2:
            return next(iter(by_key.values()), None)
        scored = {k: self._score(c, a, explicit_this, rtype) for k, c in by_key.items()}
        if any(v is None for v in scored.values()) or len({len(v) for v in scored.values()}) != 1:
            return None
        best = [k for k, v in scored.items()
                if all(all(x >= y for x, y in zip(v, w)) and v != w for k2, w in scored.items() if k2 != k)]
        return by_key[best[0]] if len(best) == 1 else None

    def accepts(self, sym: dict, a: "_Args", explicit_this: bool = False) -> bool:
        """False only when an argument's certain type cannot convert to the parameter at its position."""
        if a.types is None or a.named or not sym.get("pfull"):
            return True
        ps = sym["pfull"]
        if sym.get("ext") and not explicit_this:
            ps = ps[1:]
        gp = set(sym.get("gparams") or ()) | self.type_gparams.get(sym.get("type_q"), set())
        for i, at in enumerate(a.types):
            if at is None:
                continue
            if i < len(ps):
                p = ps[i]
            elif ps and ps[-1]["params"]:
                p = ps[-1]
            else:
                continue
            pt = p["t"]
            ok = self.compatible(at, pt, gp)
            if not ok and p["params"] and pt and pt[0] == "Array" and pt[1]:
                ok = self.compatible(at, pt[1][0], gp)
            if not ok:
                return False
        return True

    def _repo_ancestors(self, name: str) -> tuple[set[str], bool]:
        """(names a repository type `name` is, as far as known; whether some outside base is not in the table)."""
        qs = sorted({t["qparts"] for t in self.types.get(name, [])})
        names = set().union(*(self.ancestors(q) for q in qs)) if qs else {name}
        out, unknown = set(names), False
        for b in names:
            if b not in self.types:
                if dotnet.known(b):
                    out |= dotnet.ancestors(b)
                else:
                    unknown = True
        return out, unknown

    def compatible(self, at, pt, gp: set[str]) -> bool:
        """Whether an argument of type `at` may be passed where `pt` is expected. False only when certain."""
        if at is None or pt is None:
            return True
        a, p = at[0], pt[0]
        if a == "Expression" and at[1]:
            a = "LambdaExpression"                                # `Expression<TDelegate>` derives from LambdaExpression
        if p in gp or p in ("object", "Object", "dynamic") or p == a:
            return True
        p_repo = p in self.types and p not in self.implicit
        p_prim = p in dotnet.PRIMITIVES
        p_deleg = p in dotnet.DELEGATES
        p_known = dotnet.known(p)
        if a == "#lambda":
            return not (p_prim or (p in self.types) or (p_known and not p_deleg))
        literal = {"#number": dotnet.NUMERIC, "bool": {"bool", "Boolean"}, "char": {"char"} | dotnet.NUMERIC,
                   "string": {"string", "String"}}
        if a in literal or (a in dotnet.PRIMITIVES and a not in self.types):
            fits_p = literal.get(a) or ({a} | (dotnet.NUMERIC if a in dotnet.NUMERIC else set()))
            if a == "#number" and p in self.enums:
                return True                                       # `0` converts to any enum
            if p in fits_p:
                return True
            if a in ("string", "String") and p_known:
                return p in dotnet.ancestors("string") or p in ("ReadOnlySpan", "ReadOnlyMemory")
            return not (p_prim or p_deleg or p_repo or p_known)
        if a in self.types:                                       # a repository type
            names, unknown = self._repo_ancestors(a)
            if p in names or a in self.implicit:
                return True
            if p_prim or p_deleg or p_repo:
                return False
            return unknown or not p_known
        if dotnet.known(a):                                       # a .NET type the table knows
            if p in dotnet.ancestors(a) or p in dotnet.CONVERTS.get(a, ()):
                return True
            return not (p_repo or p_prim or p_deleg or p_known)
        return True       # a type we cannot see (a generic parameter, an outside type the table lacks): no ruling out

    def member(self, tq: tuple[str, ...], name: str, n=None, seen: frozenset = frozenset(),
               explicit_this: bool = False) -> dict | None:
        """The member `name` of type `tq` (or of its bases, class base first) that accepts `n` arguments. A type
        whose members of that name accept none of them hides nothing: the search goes on to its bases."""
        if tq in seen or len(seen) > 8:
            return None
        here = self.members.get((tq, name), [])
        fitting = [c for c in here if self.fits(c, n, explicit_this)]
        if fitting:
            one = self._one(fitting) or self.better(fitting, n, explicit_this)
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

    def is_repo_type(self, name: str | None, nargs: int | None = None) -> bool:
        """Whether `name` (seen with `nargs` generic arguments) is a repository type. A repository type that happens to
        share a .NET name (EF Core's own `List`) is not the receiver `List<(string, string?)>` when the argument
        counts differ; that one is .NET's."""
        if not name or name not in self.types:
            return False
        if not nargs:
            return True
        # each declaration's own arity: `Foo<T>` and `Foo<T, U>` are different types sharing a name (FluentValidation's
        # IValidationRuleInternal, Polly's AsyncSerializingCacheProvider), and the merged view keeps only one list
        return any(len(t.get("tgparams_list") or []) == nargs for t in self.types[name])

    def dotnet_member(self, rtype: str | None, near: tuple[str, ...], nargs: int | None = None) -> set[str]:
        """Instance method names the receiver has from .NET (its own type if outside, or its outside bases)."""
        if not rtype:
            return set()
        if not self.is_repo_type(rtype, nargs):
            return dotnet.members(rtype) or set()
        names, _ = self._repo_ancestors(rtype)
        return set().union(*((dotnet.members(b) or set()) for b in names if b not in self.types))

    def extension(self, name: str, n, rtype: str | None, near: tuple[str, ...], nargs: int | None = None) -> dict | None:
        """The extension method `x.name(...)` means: among those so named that accept `n` arguments, the one whose
        `this` type fits the receiver. Receiver of a repository type: its own type, a base or an interface, or a
        generic parameter. Of an outside type (whose bases the repository cannot show): its name, `I` + its name
        (`ServiceCollection` → `IServiceCollection`) or a generic parameter. Unknown receiver: only when the name
        alone names one method, and it accepts the arguments.

        The argument count only ever rules candidates out; it never makes a choice. Narrowing several `Contains`
        extensions to the one taking one argument would send every `list.Contains(x)` to it (found on Jellyfin)."""
        every = self.ext.get(name, [])
        if name in dotnet.LINQ_ALL:
            # C#: on a generic sequence LINQ's `this IEnumerable<T>` beats an extension on the non-generic IEnumerable
            # (EF Core: `query.ToList()` on an IQueryable<Blog> is LINQ's, not EF's `ToList(this IEnumerable)`)
            every = [c for c in every if not (c.get("this_type") == "IEnumerable" and not any(
                p.get("this") and p["t"] and p["t"][1] for p in c.get("pfull") or []))]
        cands = [c for c in every if self.fits(c, n)]
        # `this T` (a generic parameter) and `this object` accept any receiver
        generic = [c for c in cands if c.get("this_type") in generic_names(c)]
        if rtype and self.is_repo_type(rtype, nargs):
            # A repository type; when several share the name (Jellyfin: two `Series`), the call compiles against one
            # of them, so a candidate fitting any of their hierarchies is the only one that can be meant.
            rq = self.type_named(rtype, near)
            qs = [rq] if rq else sorted({t["qparts"] for t in self.types[rtype]})
            names = set().union(*(self.ancestors(q) for q in qs))
            pool = [c for c in cands if c.get("this_type") in names] or generic
            return self._one(pool) or self.better(pool, n, False, rtype)
        # an instance method of some repository type, so named and taking these arguments, could be the target
        shared = any(self.fits(c, n) for c in self.instance_methods.get(name, []))
        if rtype:
            # An outside type. Its exact name in `this` is safe, and so (round 3) is any ancestor the .NET table
            # knows (`StreamReader` -> `TextReader`). `this object` or `this T` only when no repository type has an
            # ordinary method of that name either (Polly: `restClient.ExecuteAsync(request)` is RestSharp's).
            # (`object` is not among them here: the table's member lists are not complete enough to say a type has
            # no method of that name, so a `this object` extension keeps the stricter rule below)
            anc = (dotnet.ancestors(rtype) - {"object"}) if dotnet.known(rtype) else {rtype}
            exact = [c for c in cands if c.get("this_type") in anc | {"I" + rtype}]
            if exact or dotnet.known(rtype):
                return self._one(exact or ([] if shared else generic))
            # a type neither the repository nor the table can show (Jellyfin's EF Core `DbSet<T>`): what is known
            # about it is no more than about an unknown receiver, so the same rule as below applies
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

    def type_sym(self, tq: tuple[str, ...]) -> dict | None:
        """One view of type `tq` across all its partial declarations (files): type parameters, base types, fields and
        properties merged. (Round 4 first took the first declaration only and lost Polly's `ResilienceContextPool
        .Shared`, declared in the other file.)"""
        cached = self._type_view.get(tq)
        if cached is not None or tq in self._type_view:
            return cached
        parts = [t for t in self.types.get(tq[-1], []) if t["qparts"] == tq]
        if not parts:
            self._type_view[tq] = None
            return None
        view = {"tgparams_list": next((t["tgparams_list"] for t in parts if t.get("tgparams_list")), []),
                "bases_full": [], "ffull": {}, "fields": {}}
        for t in parts:
            for b in t.get("bases_full") or []:
                if b not in view["bases_full"]:
                    view["bases_full"].append(b)
            view["ffull"].update(t.get("ffull") or {})
            view["fields"].update(t.get("fields") or {})
        self._type_view[tq] = view
        return view

    def chain(self, rt, near: tuple[str, ...]):
        """(type, binding) for the receiver type tree `rt` and each type it derives from, nearest first: the
        receiver's arguments bind its own parameters (`EntityTypeBuilder<Blog>` -> TEntity=Blog), and a base written
        with arguments binds the base's (`V : AbstractValidator<Person>` -> T=Person) (F1)."""
        q0 = self.type_named(rt[0], near) if rt else None
        if not q0:
            return
        todo, seen = [(q0, rt[1])], set()
        while todo and len(seen) < 16:
            q, args = todo.pop(0)
            if q in seen:
                continue
            seen.add(q)
            ts = self.type_sym(q) or {}
            params = ts.get("tgparams_list") or []
            binding = {p: a for p, a in zip(params, args) if a is not None} if len(params) == len(args) else {}
            yield q, binding
            for bt in ts.get("bases_full") or []:
                bq = self.type_named(bt[0], q[:-1])
                if bq:
                    todo.append((bq, tuple(_subst(x, binding) for x in bt[1])))

    def binding_for(self, member: dict, rt, near: tuple[str, ...]) -> dict:
        """The class-level binding under which `member` (declared on some type) is seen from receiver type `rt`."""
        dq = member.get("type_q")
        for q, binding in self.chain(rt, near):
            if q == dq:
                return binding
        return {}

    def field_bound(self, t, prop: str, near: tuple[str, ...]):
        """The type of property or field `prop` on a value of type tree `t`, its generic parameters bound."""
        for q, binding in self.chain(t, near):
            ts = self.type_sym(q) or {}
            if prop in (ts.get("ffull") or {}):
                return _subst(ts["ffull"][prop], binding)
            if prop in ts.get("fields", {}):
                return (ts["fields"][prop], ())
        if t and t[0] not in self.types:                 # an outside generic: `Lazy<T>.Value` (table)
            idx = dotnet.GENERIC_MEMBERS.get(t[0], {}).get(prop)
            if idx is not None and len(t[1]) > idx:
                return t[1][idx]
        return None

    def field_full(self, tq: tuple[str, ...] | None, name: str, seen: frozenset = frozenset()):
        """The parsed type of field or property `name` of `tq` or its bases."""
        if not tq or tq in seen or len(seen) > 16:
            return None
        for t in self.types.get(tq[-1], []):
            if t["qparts"] == tq:
                if name in (t.get("ffull") or {}):
                    return t["ffull"][name]
                if name in t.get("fields", {}):
                    return (t["fields"][name], ())
        for b in self.bases(tq):
            bq = self.type_named(b, tq[:-1])
            if bq and bq != tq:
                found = self.field_full(bq, name, seen | {tq})
                if found:
                    return found
        return None

    def constructor(self, name: str, near: tuple[str, ...], n=None) -> dict | None:
        tq = self.type_named(name, near)
        if not tq:
            return None
        return self._one([c for c in self.members.get((tq, "ctor"), []) if self.fits(c, n)]) or self._one(
            [t for t in self.types.get(tq[-1], []) if t["qparts"] == tq])


_CALL = re.compile(r"(?P<new>\bnew\s+)?(?P<chain>@?[^\W\d]\w*(?:\s*\??\.\s*@?[^\W\d]\w*)*)\s*"
                   r"(?:<[^<>();{}]*(?:<[^<>();{}]*>[^<>();{}]*)*>)?\s*\(")
_LOCAL = re.compile(r"(?:^|[;{(\s,])(?!(?:using|await|return|yield|throw|new|else|case|in|is|as|out|ref|const|"
                    r"static|readonly|fixed|unsafe|checked|lock|foreach|for|while|if|scoped)\s)"
                    r"(?:var|(?P<t>[^\W\d][\w.]*(?:<[^;=(){}]*>)?)\??(?P<arr>\[\])?)\s+@?(?P<n>[^\W\d]\w*)\b(?!\s*[(<])"   # `T Name(`: a local function, not a variable
                    r"\s*(?:=\s*new\s+(?P<nt>[^\W\d][\w.]*(?:<[^;=(){}]*?>)?)\s*[({])?")


def _last_word(s: str) -> str | None:
    """The identifier `s` ends with (as `re.search(r"[^\W\d]\w*$", s)` reads it), or None. A backward scan: the
    regex tries every position of the window, once per call site (#61)."""
    j = len(s)
    while j and (s[j - 1].isalnum() or s[j - 1] == "_"):
        j -= 1
    while j < len(s) and s[j].isdecimal():
        j += 1
    return s[j:] or None


def _new_ends_statement(body: str, k: int) -> bool:
    """Whether the `new T(...)` / `new T { ... }` whose `(` or `{` is at body[k] is the whole value: after its
    argument list and initializer comes `;` (or `,`/`)` in a `using` or `for` header), not `.Member`."""
    j = k
    for _ in range(2):                                   # `(...)`, then an optional `{...}` initializer
        if j >= len(body) or body[j] not in "({":
            break
        depth, start = 0, j
        while j < len(body) and j - start < _ARG_SCAN:
            if body[j] in "([{":
                depth += 1
            elif body[j] in ")]}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        j += 1
        while j < len(body) and body[j].isspace():
            j += 1
    return j < len(body) and body[j] in ";,)"


def _locals_full(body: str) -> dict[str, tuple]:
    """{local or parameter name: parsed type} for declarations in `body` (`T x`, `var x = new T(...)`)."""
    out: dict[str, tuple] = {}
    for m in _LOCAL.finditer(body):
        if m.group("nt") and not _new_ends_statement(body, m.end() - 1):
            continue                    # `var s = new B { ... }.ToString();`: the value is not a B (EF Core)
        text = m.group("nt") or (m.group("t") + (m.group("arr") or "") if m.group("t") else None)
        t = _pt(text) if text else None
        if t and t[0] not in _NOT_CALL and m.group("n") not in _NOT_CALL:
            out.setdefault(m.group("n"), t)
    for rx, ti, ni in ((_DECL_CAST, 2, 1), (_DECL_AS, 2, 1), (_DECL_PATTERN, 1, 2), (_DECL_PATTERN, 3, 4)):
        for m in rx.finditer(body):
            if not m.group(ti):
                continue
            t = _pt(m.group(ti))
            if t and t[0] not in _NOT_CALL and t[0] not in ("null", "var", "not", "and", "or") \
                    and m.group(ni) not in _NOT_CALL:
                out.setdefault(m.group(ni), t)
    return out


def _locals(body: str) -> dict[str, str]:
    return {k: v[0] if v[0] != "Array" else (v[1][0][0] if v[1] and v[1][0] else "Array")
            for k, v in _locals_full(body).items()}


# Only the text just before a call decides how to read it; slicing the whole body prefix per call was quadratic
# (a 1 MB generated method in EF Core did not finish in 5 minutes).
_LOOKBACK = 256

_KEEP_BEFORE = frozenset("return await yield throw new in is as case when else "
                         # query keywords (F4): `where x.M()`, `select c.Name()`, `orderby x.Key()`, `on a.Id() equals ...`
                         "where select orderby ascending descending on equals by into let group join from".split())


def _why(m, before: str, parts: list[str], rtype: str | None, name: str, index: "_Index") -> str:
    """Why a call to a name the repository defines got no edge (for `stats`; the graph does not store it)."""
    if m.group("new"):
        return "new-ambiguous-type"
    if before.endswith(".") or before.endswith(")"):
        return "chained"                                         # `a.B().C()`: the receiver is a call's result
    if len(parts) == 1:
        return "bare-not-in-type"                                # inherited from an outside base, or `using static`
    if index.several("ext", name):
        return "extension-ambiguous"                             # several extension methods share the name
    if rtype:
        return "receiver-type-lacks-member"
    if index.several("by_name", name):
        return "receiver-unknown-ambiguous"                      # receiver's type unknown, several targets
    return "receiver-unknown-single"


_VAR_BEFORE = re.compile(r"\bvar\s+@?(?P<n>[^\W\d]\w*)\s*=\s*(?P<aw>await\s+)?$")
_FOREACH_BEFORE = re.compile(r"\bforeach\s*\(\s*var\s+@?(?P<n>[^\W\d]\w*)\s+in\s+(?P<aw>await\s+)?$")
_AFTER_PROPS = re.compile(r"^((?:\s*!?\s*\??\.\s*@?[^\W\d]\w*)+)\s*;")
_AFTER_STMT = re.compile(r"^\s*(?:\.\s*ConfigureAwait\s*\([^()]*\)\s*)?;")
_AFTER_FOREACH = re.compile(r"^\s*(?:\.\s*ConfigureAwait\s*\([^()]*\)\s*)?\)")
_FOREACH_LOCAL = re.compile(r"\bforeach\s*\(\s*var\s+@?(?P<n>[^\W\d]\w*)\s+in\s+@?(?P<src>[^\W\d]\w*)\s*\)")


def _awaited(body: str, q: int, results: dict):
    """`(await <call>)` closing at body[q]: (the call's result type unwrapped, where the expression starts)."""
    depth, j, lo = 0, q, max(0, q - _ARG_SCAN)
    while j >= lo:
        c = body[j]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            depth -= 1
            if depth == 0:
                break
        j -= 1
    if j < lo or body[j] != "(":
        return None
    inner = body[j + 1:q]
    if not re.match(r"\s*await\s", inner):
        return None
    tail = inner.rstrip()
    cm = re.search(r"\)\s*\.\s*ConfigureAwait\s*\([^()]*\)$", tail)
    end = j + 1 + (cm.start() if cm else len(tail) - 1)
    r = results.get(end)
    return (_unwrap(r[0]), j) if r and r[0] else None


def _calls_in(s: dict, masked: str, nl: list[int], index: _Index, locals_fns: dict[str, dict], raw: str = "",
              aliases: dict | None = None):
    """Yield (callee or None, confidence, line, text, why) for each call in `s`'s bodies; `why` is "resolved", or
    the reason it is not (see `_why`).

    Round 3: expressions are typed as the calls are visited left to right. Each call that resolves records its
    result type at its closing parenthesis, so `a.B().C()`, `(await a.B()).C()`, `var x = a.B();` and
    `foreach (var x in a.B())` type what follows; a lambda passed to a resolved method gets its parameters typed from
    the delegate it is passed as, for the span of its body; `x.P.Q.M()` walks property types."""
    tq = s.get("type_q") or ()
    nested = [span for f in locals_fns.values() for span in f.get("body", [])]   # a local function's calls are its own
    for start, end in s["body"]:
        body = masked[start:end]
        rbody = raw[start:end] if raw else body
        types: dict[str, tuple] = {k: (v, ()) for k, v in s.get("params", {}).items()}
        types.update({p["name"]: p["t"] for p in s.get("pfull") or [] if p.get("t")})
        types.update({k: _dealias(v, aliases) for k, v in _locals_full(body).items()})
        inferred: set[str] = set()                                # locals typed from a call's result (var, foreach)
        for fm in _FOREACH_LOCAL.finditer(body):                  # foreach (var x in items)
            el = _elem(types.get(fm.group("src")) or (index.field_full(tq, fm.group("src")) if tq else None))
            if el:
                types.setdefault(fm.group("n"), el)
                inferred.add(fm.group("n"))
        results: dict[int, tuple] = {}                            # close paren -> (result type, expression start)
        # lambda parameters, by name: [(from, to, type, declared, the largest `to` so far)]. By name, and a lookup
        # stops where no earlier span reaches its position: one list scanned whole was quadratic in long fluent
        # methods (EF Core model snapshots, #61)
        scoped: dict[str, list[tuple]] = {}

        def scope(a0: int, b0: int, nm: str, t, declared: bool) -> None:
            entries = scoped.setdefault(nm, [])
            entries.append((a0, b0, t, declared, max(b0, entries[-1][4]) if entries else b0))

        cons = {}
        for k in range(1, len(tq) + 1):                           # enclosing types' constraints, then the method's
            cons.update(index.type_cons.get(tq[:k], {}))
        cons.update(s.get("gcons") or {})

        def constrained(t):
            """A generic parameter is, as far as calls go, its constraint (`TContext : DbContext`)."""
            return (cons[t[0]], ()) if t and t[0] in cons else t

        def type_of(nm: str, pos: int, declared_only: bool = False):
            """`nm`'s type at `pos`. With `declared_only` (to rule an argument out), only a type the source writes:
            an inferred one (a call's result, a delegate's parameter) may be off, and a wrong ruling-out loses a
            correct edge (found on EF Core)."""
            for a0, b0, t, declared, reach in reversed(scoped.get(nm, ())):
                if reach <= pos:
                    break                                         # no earlier span reaches `pos`
                if a0 <= pos < b0:
                    # (None: untyped, still shadows); a type parameter is its constraint here too (EF Core: the
                    # lambda's `e` of type `TExtension : RelationalOptionsExtension`)
                    return constrained(t) if (declared or not declared_only) else None
            if nm in types:
                return None if declared_only and nm in inferred else constrained(types[nm])
            return constrained(index.field_full(tq, nm)) if tq else None

        guessed = [False]

        def brace_close(k: int) -> int | None:
            depth = 0
            for j in range(k, min(len(body), k + _ARG_SCAN)):
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return j
            return None

        # `new T { ... }` (no argument list): its value, recorded where the initializer closes, so a chained
        # `.M()` after it is typed (Jellyfin: `var o = new DtoOptions { Fields = f }.AddClientFields(User);`)
        for nm_ in re.finditer(r"\bnew\s+([^\W\d][\w.]*(?:<[^<>(){};]*>)?)\s*\{", body):
            close = brace_close(nm_.end() - 1)
            if close is not None:
                results[close] = (_dealias(_pt(nm_.group(1)), aliases), nm_.start())

        def expr_type(o: int):
            """The type of the expression just before body[o] (an indexer's `[`): a call's result, or a name and its
            property chain."""
            lhs = body[max(0, o - _LOOKBACK):o].rstrip()
            if lhs.endswith(")"):
                j = o - 1
                while j > 0 and body[j].isspace():             # bounded: no copy of the body's prefix
                    j -= 1
                r = results.get(j)
                return r[0] if r else None
            cm = re.search(r"(?<![\w.])(this\.)?@?([^\W\d]\w*)((?:\s*\??\.\s*@?[^\W\d]\w*)*)$", lhs)
            if not cm:
                return None
            props = [p_ for p_ in re.sub(r"[\s?@]", "", cm.group(3)).split(".") if p_]
            return walk(type_of(cm.group(2), o), props)

        def cast_at(q: int):
            """`((T)x).M()` or `(x as T).M()`: (T, start) for the parenthesised expression closing at body[q]."""
            o = _open_of(body, q)
            if o is None:
                return None
            inner = body[o + 1:q]
            cm = _CAST.match(inner) or _AS.search(inner)
            return ((_dealias(_pt(cm.group(1)), aliases), o) if cm else None)

        def walk(t, props):
            guessed[0] = False
            for prop in props:
                if t is None:
                    return None
                t = constrained(t)
                q = index.type_named(t[0], tq)
                nt = constrained(index.field_bound(t, prop, tq))
                if nt is None and prop in index.types:
                    nt = (prop, ())          # "Color Color": a property named like a type is of that type (EF Core:
                    guessed[0] = True        # `Fixture.TestSqlLoggerFactory`); only when the lookup itself failed
                t = nt
            return t

        # F4: `from x in src` / `join y in src2`: x and y are elements of their source, for the rest of the query
        for qm in re.finditer(r"\b(?:from|join)\s+(?:([^\W\d][\w.]*(?:<[^<>()]*>)?)\s+)?@?([^\W\d]\w*)\s+in\s+"
                              r"(this\.)?@?([^\W\d]\w*)((?:\s*\??\.\s*@?[^\W\d]\w*)*)", body):
            if qm.group(1) in ("var",):
                continue
            end_q = body.find(";", qm.end())
            end_q = len(body) if end_q < 0 else end_q
            if qm.group(1):
                el = _dealias(_pt(qm.group(1)), aliases)
                declared = True
            else:
                props = [p_ for p_ in re.sub(r"[\s?@]", "", qm.group(5)).split(".") if p_]
                el, declared = _elem(walk(type_of(qm.group(4), qm.start()), props)), False
            scope(qm.start(), end_q, qm.group(2), el, declared)

        for m in _CALL.finditer(body):
            at = start + m.start()
            if any(a <= at < b for a, b in nested if not (a <= start and end <= b)):
                continue
            off = max(0, m.start() - _LOOKBACK)
            window = body[off: m.start()]
            pre = window.rstrip()
            word = _last_word(pre)
            if not m.group("new") and ((word and word not in _KEEP_BEFORE and not pre.endswith("."))
                                       or (pre.endswith(">") and not pre.endswith("=>") and not pre.endswith("->"))):
                continue                                          # `T Name(...)`: a declaration, not a call
            chain = re.sub(r"\s+|\?", "", m.group("chain")).replace("@", "")
            parts = chain.split(".")
            name = parts[-1]
            if name in _NOT_CALL and not m.group("new"):
                continue
            before = pre
            line = bisect_left(nl, start + m.end("chain") - 1) + 1     # the name's line, not the chain's first
            found, rt, rtype, static, dotnet_bound, explicit = None, None, None, False, False, False
            index.ambiguous = False
            guessed[0] = False
            a_ = _args(body, rbody, m.end() - 1)
            if a_.items is not None:
                a_.types = [_dealias(_arg_type(mi, ri, lambda nm, pos=ai: type_of(nm, pos, True)), aliases)
                            for mi, ri, ai, _bi in a_.items]
            if a_.items:                                          # untyped first; typed entries added later win
                for mi, _ri, ai, bi in a_.items:
                    lm = _LAMBDA.match(mi)
                    if lm:
                        for part in (_split_top(lm.group("ps")) if lm.group("ps") is not None else [lm.group("p")]):
                            toks = _split_top(part.strip(), " ")
                            declared = _dealias(_pt("".join(toks[:-1])), aliases) if len(toks) > 1 else None
                            scope(ai, bi, toks[-1].lstrip("@"), declared, declared is not None)
            expr_start = m.start()
            chained = False
            generic_static = None                                 # F6: `Type<A>.M(...)`
            if not m.group("new") and before.endswith("."):
                left = before[:-1].rstrip()
                left = left[:-1].rstrip() if left.endswith(("?", "!")) else left
                q = off + len(left) - 1
                gm_ = _GENERIC_TYPE_END.search(left) if left.endswith(">") else None
                if gm_ and gm_.group(1).split(".")[-1][:1].isupper():
                    generic_static = (gm_.group(1).split(".")[-1], tuple(_pt(x) for x in _split_top(gm_.group(2))))
                elif left.endswith("]") and (o := _open_of(body, q)) is not None:
                    inner_t = expr_type(o)                        # F7: `x[i].M()`
                    el = _index_elem(inner_t)
                    if el:
                        chained, rt = True, walk(el, parts[:-1])
                    else:
                        chained = None
                elif left.endswith((")", "}")):
                    r = results.get(q) or _awaited(body, q, results) or cast_at(q)
                    if r and r[0]:
                        chained = True
                        rt = walk(r[0], parts[:-1])
                        expr_start = r[1]
                    else:
                        chained = None
                else:
                    chained = None
            new_type = None
            if m.group("new"):
                gm = re.match(r"new\s+([^(]*)\(", m.group(0))
                new_type = _dealias(_pt(gm.group(1)), aliases) if gm else None
                hit = index.constructor(name, tq, a_)
                found = (hit, 0.6) if hit else None
            elif generic_static is not None:
                gname = generic_static[0]
                if (bq := index.type_named(gname, tq)) is not None and len(parts) == 1:
                    static = explicit = True
                    hit = index.member(bq, name, a_, explicit_this=True)
                    found = (hit, 0.7) if hit else None
                    rt = (gname, generic_static[1])
                elif dotnet.static_member(gname, name):
                    dotnet_bound = True
            elif chained is None:
                found = None                                      # a call on an expression we cannot type
            elif chained:
                rtype = rt[0] if rt else None
            elif len(parts) == 1:
                explicit = True
                hit = locals_fns.get(name) or (index.member(tq, name, a_, explicit_this=True) if tq else None)
                found = (hit, 0.8) if hit else None
                if found is None and tq and not index.ambiguous and name in index.dotnet_member(tq[-1], tq):
                    dotnet_bound = True                           # `Ok(x)` in a ControllerBase: MVC's own method
            else:
                if parts[0] == "this" and len(parts) > 2:
                    parts = parts[1:]                             # `this.field.M()` is `field.M()`
                recv, rest = parts[0], parts[1:-1]
                if recv in ("this", "base") and not rest:
                    if recv == "this":
                        hit = index.member(tq, name, a_) or index.extension(name, a_, tq[-1] if tq else None, tq)
                    else:
                        hit = next((h for b in index.bases(tq) if (bq := index.type_named(b, tq))
                                    and (h := index.member(bq, name, a_))), None)
                    found = (hit, 0.8) if hit else None
                else:
                    rt0 = type_of(recv, m.start())
                    if rt0:
                        rt = walk(rt0, rest)
                        rtype = rt[0] if rt else None
                    elif not rest and recv not in index.types and dotnet.static_member(recv, name):
                        dotnet_bound = True                       # `Path.GetExtension(p)`: .NET's own static method
                    elif recv[:1].isupper() and (bq := index.type_named(recv, tq)):
                        if not rest:
                            static = explicit = True
                            hit = index.member(bq, name, a_, explicit_this=True)   # `Type.Member(...)`: static
                            found = (hit, 0.7) if hit else None
                        else:
                            rt = walk((recv, ()), rest)            # `Type.StaticProperty.M()`
                            rtype = rt[0] if rt else None
                    if found is None and rt0 is None and rtype is None and rest and rest[-1][:1].isupper() and \
                            (bq := index.type_named(rest[-1], tq)):
                        static = explicit = True
                        hit = index.member(bq, name, a_, explicit_this=True)       # `Ns.Type.Member(...)`
                        found = (hit, 0.6) if hit else None
            if rtype == "dynamic":
                dotnet_bound = True                               # F3: bound at run time; not a repository call
                rtype = None
            if rtype and found is None:
                bq = index.type_named(rtype, tq) if index.is_repo_type(rtype, len(rt[1]) if rt else None) else None
                hit = index.member(bq, name, a_) if bq else None
                found = (hit, 0.7) if hit else None
                collection_arg = any(mi.strip().startswith("[") for mi, *_ in (a_.items or []))
                if found is None and not index.ambiguous and not collection_arg and \
                        name in index.dotnet_member(rtype, tq, len(rt[1]) if rt else None):
                    # (a collection expression `[x]` may not convert to the .NET member's parameter, while a
                    # repository extension taking IEnumerable<T> does: EF Core `queue.Enqueue([failure])`)
                    dotnet_bound = True                           # C#: the receiver's own .NET method wins
            if found is None and not index.ambiguous and not dotnet_bound and not m.group("new") \
                    and chained is not None and (len(parts) > 1 or chained):
                # `x.Ext()`: chosen by arguments and receiver; a failed `Type.M()` may be a property sharing a type's
                # name (`User.GetUserId()`)
                ext_rtype = "LambdaExpression" if rt and rt[0] == "Expression" and rt[1] else rtype   # F9
                ext = index.extension(name, a_, None if static else ext_rtype, tq, len(rt[1]) if rt else None)
                if ext is None and rtype and guessed[0]:
                    ext = index.extension(name, a_, None, tq)    # the guessed type was wrong: as an unknown receiver
                found = (ext, 0.6 if rtype else 0.5) if ext else None
            callee = found[0] if found else None
            if callee is not None and callee["key"] == s["key"]:
                callee, found = None, None
                recursion = True
            else:
                recursion = False
            # what the call returns, and its lambdas' parameter types
            res = new_type
            if callee is not None:
                ovs = [o for o in index.by_key.get(callee["key"], [callee]) if index.fits(o, a_, explicit)] or [callee]
                # F1: the class binding seen from the receiver (or from this type itself for a bare call), and the
                # method's own: explicit `<...>` in the call, else inferred from the arguments' and receiver's types
                self_rt = (tq[-1], tuple((g, ()) for g in (index.type_sym(tq) or {}).get("tgparams_list") or [])) \
                    if tq else None
                recv_rt = rt if rt is not None else (self_rt if len(parts) == 1 or parts[0] in ("this", "base") else None)
                gtext = body[m.end("chain"):m.end() - 1].strip()
                explicit_args = [_pt(x) for x in _split_top(gtext[1:-1])] if gtext.startswith("<") else []
                any_types = ([_dealias(_arg_type(mi, ri, lambda nm, pos=ai: type_of(nm, pos)), aliases)
                              for mi, ri, ai, _bi in a_.items] if a_.items else [])

                def bound(o):
                    b = dict(index.binding_for(o, recv_rt, tq)) if recv_rt and o.get("type_q") else {}
                    gl = o.get("gparams_list") or []
                    if explicit_args and len(explicit_args) == len(gl):
                        b.update({g: a__ for g, a__ in zip(gl, explicit_args) if a__})
                    elif gl:
                        ps_ = o.get("pfull") or []
                        mb: dict = {}
                        if o.get("ext") and not explicit and ps_ and rt is not None:
                            _unify(ps_[0]["t"], rt, set(gl), mb)            # `this IEnumerable<T>` <- the receiver
                            ps_ = ps_[1:]
                        for p_, at_ in zip(ps_, any_types):
                            _unify(p_["t"], at_, set(gl), mb)
                        b.update(mb)
                    return b
                rets = set()
                for o in ovs:
                    if o["name"] == "ctor" or o["kind"] in ("class", "enum"):
                        t = new_type or (o["type_q"][-1] if o["name"] == "ctor" else o["name"], ())
                    else:
                        t = _subst(o.get("ret_full"), bound(o))
                        if t and t[0] in (o.get("gparams") or ()):
                            t = rt if (o.get("ext") and not explicit and o.get("this_type") == t[0]) else None
                        elif t and t[0] in index.type_gparams.get(o.get("type_q"), set()):
                            t = None
                        if t and t[0] in ("void", "Void"):
                            t = None
                    rets.add(t)
                if len(rets) == 1:
                    res = rets.pop()
                elif None not in rets and len({t[0] for t in rets}) == 1:
                    # overloads agree on the type and differ only in how much of its arguments is bound (F1: a
                    # generic overload binds `TResult`, its non-generic sibling cannot; Polly `HandleResult(...).Or()`)
                    gnames: set[str] = set()
                    for o in ovs:
                        gnames |= set(o.get("gparams") or ()) | index.type_gparams.get(o.get("type_q"), set())
                    unbound = lambda t: sum(1 for x in t[1] if x is None or (not x[1] and x[0] in gnames))  # noqa: E731
                    res = min(rets, key=lambda t: (unbound(t), str(t)))
                else:
                    res = None
                if a_.items:
                    skip = 1 if callee.get("ext") and not explicit else 0
                    for i, (mi, _ri, ai, bi) in enumerate(a_.items):
                        lm = _LAMBDA.match(mi)
                        if not lm:
                            continue
                        names = ([w.split()[-1] for w in lm.group("ps").split(",") if w.strip()]
                                 if lm.group("ps") is not None else [lm.group("p")])
                        cand = set()
                        for o in ovs:
                            ps = (o.get("pfull") or [])[skip if o.get("ext") else 0:]
                            lt = _lambda_param_types(_subst(ps[i]["t"], bound(o)), len(names)) if i < len(ps) else None
                            gp = set(o.get("gparams") or ())
                            cand.add(tuple(None if (x is None or x[0] in gp) else x for x in lt) if lt else None)
                        if len(cand) == 1 and (lt := cand.pop()):
                            for nm, t in zip(names, lt):
                                if t:
                                    scope(ai, bi, nm.lstrip("@"), t, False)
            if callee is None and rt is not None and not m.group("new"):
                # an outside method on a typed receiver: LINQ over a known element type, or a fluent builder
                el = _elem(rt)
                if el is not None and name in dotnet.LINQ_LAMBDA and a_.items:
                    for mi, _ri, ai, bi in a_.items:
                        lm = _LAMBDA.match(mi)
                        if lm and lm.group("p"):
                            scope(ai, bi, lm.group("p").lstrip("@"), el, False)
                if el is not None and name in dotnet.LINQ_SAME:
                    res = ("IEnumerable", (el,))
                elif el is not None and name in dotnet.LINQ_ELEMENT:
                    res = el
                elif el is not None and name in dotnet.LINQ_TO:
                    res = (dotnet.LINQ_TO[name], (el,))
                elif rt[0] in dotnet.FLUENT_SELF:
                    res = rt
            if res is not None and a_.close is not None and m.group("new"):
                after = a_.close + 1                              # `new T(...) { ... }`: the value ends at `}`
                while after < len(body) and body[after].isspace():
                    after += 1
                if after < len(body) and body[after] == "{" and (bc := brace_close(after)) is not None:
                    results[bc] = (res, expr_start)
            if res is not None and a_.close is not None:
                results[a_.close] = (res, expr_start)
                head = body[max(0, expr_start - _LOOKBACK): expr_start]
                tail = body[a_.close + 1: a_.close + 80]
                vm = _VAR_BEFORE.search(head)
                pm = _AFTER_PROPS.match(tail) if vm and not _AFTER_STMT.match(tail) else None
                if vm and (_AFTER_STMT.match(tail) or pm):
                    t = _unwrap(res) if vm.group("aw") else res
                    if t and pm:                                  # `var x = a.B().C;`: the value is a property of it
                        t = walk(t, [p_ for p_ in re.sub(r"[\s!?@]", "", pm.group(1)).split(".") if p_])
                    if t:
                        types[vm.group("n")] = t
                        inferred.add(vm.group("n"))
                fe = _FOREACH_BEFORE.search(head)
                if fe and _AFTER_FOREACH.match(tail):
                    t = _elem(_unwrap(res) if fe.group("aw") else res)
                    if t:
                        types[fe.group("n")] = t
                        inferred.add(fe.group("n"))
            if recursion:
                continue                                          # recursion: not an edge, not unresolved
            if found:
                yield found[0], found[1], line, chain, "resolved"
            elif dotnet_bound:
                yield None, 0.0, line, name, "external"           # the receiver's own .NET method
            elif name in index.by_name:
                why = "chained" if chained is None else _why(m, before, parts, rtype if len(parts) > 1 else None,
                                                             name, index)
                yield None, 0.0, line, name, why
            else:
                yield None, 0.0, line, name, "external"           # no symbol of that name in the repository


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
    fn_q: set[tuple[str, ...]] = set()
    for x in symbols:
        if x["kind"] == "function":
            local_fns.setdefault(x["qparts"][:-1], {})[x["name"]] = x
            fn_q.add(x["qparts"])
    for s in symbols:
        if not s.get("body"):
            continue
        sc = scans[s["rel"]]
        locals_fns = local_fns.get(s["qparts"], {})
        if s["kind"] == "function":
            # a local function also sees its siblings and those of every enclosing local function, up to the member
            # that holds them; the nearest scope wins (#58)
            q, scopes = s["qparts"][:-1], []
            while True:
                scopes.append(local_fns.get(q, {}))
                if q not in fn_q:
                    break
                q = q[:-1]
            seen: dict[str, dict] = {}
            for d in reversed(scopes):
                seen.update(d)
            seen.update(locals_fns)
            locals_fns = seen
        for callee, conf, line, text, why in _calls_in(s, sc["masked"], sc["nl"], index, locals_fns, sc["raw"],
                                                       sc.get("aliases")):
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
    summary: dict[str, tuple] = {}           # per name, once: per symbol it was (definitions x call sites) (#60)
    for s in symbols:
        if s["kind"] in ("method", "function") and s["name"] in unresolved:
            if s["name"] not in summary:
                files: dict[str, int] = {}
                for rel, _caller in unresolved[s["name"]]:
                    files[rel] = files.get(rel, 0) + 1
                summary[s["name"]] = (sum(files.values()), sorted(files, key=lambda f: (-files[f], f))[:20], len(files))
            n_calls, top, n_files = summary[s["name"]]
            s["unresolved_calls"], s["unresolved_files"], s["unresolved_file_count"] = n_calls, list(top), n_files
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
