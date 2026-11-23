"""TypeScript/TSX Symbol extraction (devkb BL-3c, body/legs model).

Regex-based, mirroring discovery/extract_typescript.py's own established
approach (no TS parser in Python's stdlib, and the factory's discovery tooling already
established regex-over-source as an acceptable tradeoff for this class of
tool -- confirmed proven and shipped, not a shortcut unique to this file).
Extracts function/component/class-level Symbols -- discovery's own
extractor only goes to file (Module) level; this is the missing piece that
made the frontend invisible to devkb entirely (BL-3 was Python-only until
now, so 0 of any registered project's real TypeScript/React code -- the
actual user-facing behavior -- was in the graph at all).

Per-Symbol, also captures get/post/put(...) API-client call sites within
that symbol's own body -- porting extract_typescript.py's CALL_RE/
QUOTED_RE/DEFAULT_BASE_PARAM_RE/CONST_STR_RE patterns verbatim (same
regexes, same reasoning already proven against pms-web/src/lib/api.ts's
real 3 helper names) rather than reinventing the same regex differently.
This is the frontend half of BL-4b's cross-language CALLS_API edge --
resolution against real backend Symbols happens in build_symbols.py, which
has visibility into both languages; this module only extracts.

**Known remaining gap, confirmed live, not silently worked around**: OCO's
own `webapp/frontend/src/lib/api.ts` routes every call through a single
generic `apiFetch<T>(path, init?)` wrapper (HTTP method carried in `init`,
defaulting to GET) rather than three separately-named `get`/`post`/`put`
helpers -- `CALL_RE` (below, ported from `discovery/extract_typescript.py`)
doesn't match that shape, so `route_calls` comes back real-but-empty for
OCO even though Symbol extraction itself (including the object-literal
fix below) now correctly finds `api.qualityScore` etc. as real Symbols.
Not fixed here: it's a materially different call shape (an `init.method`
value to parse, not a function name), and `discovery/extract_typescript.py`
itself -- the already-shipped pattern this ports from -- has the exact
same gap (confirmed: its own `CALL_RE` also finds zero matches against
this file). Extending past what's already proven and shipped elsewhere in
this codebase is a real follow-up, not this pass's job.

Deliberately narrower than a real parser: only top-level `function Name(...)`,
`const Name = (...) => {...}`, `class Name`, and object-literal-method
entries (`export const pmsApi = { overview: () => get<T>("/overview") }`)
are extracted as Symbols. The object-literal case is not cosmetic --
confirmed live against both real frontends this was built for: ODSF's own
`pms-web/src/lib/api.ts` (`pmsApi = { overview: () => get<PMSOverview>
("/overview"), ... }`) and OCO's `webapp/frontend/src/lib/api.ts`
(`api = { graphStats: () => apiFetch<T>("/graph/stats"), ... }`) BOTH
route 100% of their real API calls through this shape, not a bare
top-level `function`/arrow-const -- without object-literal-method
detection, `CALLS_API` (BL-4b) produced zero edges on either project's
actual code. A call inside a genuinely undetected symbol's body (nested
object literals beyond the outer container, computed keys, spread) is
still simply not attributed to anything, not mis-attributed to the wrong
one -- the same precision-over-recall choice BL-4 already made.
"""
from __future__ import annotations

import re
from pathlib import Path

_FUNC_DECL_RE = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(',
    re.MULTILINE,
)
_ARROW_CONST_RE = re.compile(
    r'^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>\s*\{',
    re.MULTILINE,
)
# The same head up to the `(` of the parameters, and the part after the `)` (#418): which symbols are found does not change, but a `{` that the pattern
# above found inside the parameters (`({ onConfirm = () => {} }: Props) => {`: the default value's own arrow) is not the body's.
_ARROW_HEAD_RE = re.compile(r'^\s*(?:export\s+)?const\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=\s*(?:async\s*)?\(', re.MULTILINE)
_ARROW_TAIL_RE = re.compile(r'\s*(?::[^=]+)?=>\s*\{')
_ARROW_EXPR_RE = re.compile(r'\s*(?::[^=]+)?=>')
_CLASS_RE = re.compile(r'^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)', re.MULTILINE)
_OBJECT_LITERAL_RE = re.compile(
    r'^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*\{',
    re.MULTILINE,
)
_OBJECT_METHOD_RE = re.compile(
    r'^\s*([A-Za-z_$][\w$]*)\s*:\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>\s*',
    re.MULTILINE,
)

# Ported verbatim from discovery/extract_typescript.py -- same helper-name
# convention (pms-web/src/lib/api.ts's own get/post/put), same reasoning.
CALL_RE = re.compile(r'\b(get|post|put)(?:<[^>]*>)?\(\s*[`"]([^`"]+)[`"]([^)]*)\)')
QUOTED_RE = re.compile(r'[`"]([^`"]+)[`"]')
DEFAULT_BASE_PARAM_RE = re.compile(r'base\s*=\s*([A-Za-z_$][\w$]*)')
CONST_STR_RE = re.compile(r'\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*["\']([^"\']+)["\']')

_METHOD_MAP = {"get": "GET", "post": "POST", "put": "PUT"}

# ── ODSF-314: the call shapes OCO's frontend actually uses (CALLS_API was 0 there) ──────────────────────────────
# fetch(`/api/v1/jobs/${id}`, {method: "POST"}); a wrapper `apiFetch(path)` that prefixes a module constant;
# a URL builder `acknowledgeAnomalyUrl(id)` defined in one file and passed to fetch in another.
_TEMPLATE_PARAM = re.compile(r"\$\{\s*([A-Za-z_$][\w$.]*)?[^}]*\}")
_FETCH_LITERAL = re.compile(r"\bfetch\(\s*([`\"'])(.+?)\1(.{0,240})", re.S)
_FETCH_BUILDER = re.compile(r"\bfetch\(\s*([A-Za-z_$][\w$]*)\((.{0,240})", re.S)
_METHOD_OPT = re.compile(r"method\s*:\s*[`\"'](\w+)[`\"']")
_BUILDER_FN = re.compile(r"(?:export\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*string)?\s*\{\s*return\s+([`\"'])(.+?)\2", re.S)
_BUILDER_ARROW = re.compile(r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*\([^)]*\)\s*(?::\s*string)?\s*=>\s*([`\"'])(.+?)\2", re.S)
_WRAPPER_FN = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\(\s*([A-Za-z_$][\w$]*)\s*:\s*string[^)]*\)[^{]*\{(.{0,600})", re.S)


def normalise_path(raw: str, consts: dict[str, str]) -> str | None:
    """A URL as a route-shaped path: `${CONST}` becomes the constant's value, any other `${...}` a `{}` slot, the
    query string and an origin are dropped, and a leading unknown base is dropped. None when it is not a path."""
    def sub(m):
        name = m.group(1) or ""
        return consts.get(name, "{}")
    path = _TEMPLATE_PARAM.sub(sub, raw.split("?")[0].strip())
    path = re.sub(r"^https?://[^/]+", "", path)
    while path.startswith("{}"):
        path = path[2:]
    path = path.rstrip("/")
    return path if path.startswith("/") and len(path) > 1 else None


def route_shape(path: str) -> str:
    """`/api/v1/jobs/{job_id}` and `/api/v1/jobs/{}` compare equal."""
    return re.sub(r"\{[^}]*\}|<[^>]+>", "{}", path.rstrip("/"))


def collect_url_helpers(files: list[Path]) -> tuple[dict[str, str], dict[str, str]]:
    """Repository-wide (builders, wrappers): a function returning a URL template, by name -> its path; a function
    whose first string parameter is fetched behind a module constant, by name -> that prefix."""
    builders: dict[str, str] = {}
    wrappers: dict[str, str] = {}
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        consts = dict(CONST_STR_RE.findall(text))
        for rx in (_BUILDER_FN, _BUILDER_ARROW):
            for name, _q, url in rx.findall(text):
                norm = normalise_path(url, consts)
                if norm:
                    builders.setdefault(name, norm)
        for name, param, body in _WRAPPER_FN.findall(text):
            m = re.search(r"fetch\(\s*`\$\{\s*([A-Za-z_$][\w$]*)\s*\}\$\{\s*" + re.escape(param) + r"\s*\}`", body)
            if m and m.group(1) in consts:
                wrappers.setdefault(name, consts[m.group(1)].rstrip("/"))
    return builders, wrappers


def _method(tail: str, default: str = "GET") -> str:
    m = _METHOD_OPT.search(tail.split(");")[0][:240])  # up to the end of this call, past any nested call's ")"
    return m.group(1).upper() if m else default


_REGEX_AFTER_WORD = frozenset("return typeof instanceof in of new delete void throw case do else yield await".split())
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


class _Masker:
    """The source with everything that is not code blanked, same length, newlines kept, so a brace count and a line number computed on the result are
    right for the original (#418): line and block comments, string literals, the text parts of template literals (the `${ ... }` expressions inside
    stay code, nested to any depth), regular-expression literals and, in a `.tsx`/`.jsx` file, JSX text and attribute strings. A regular expression
    is told from a division by the token before the slash; JSX from a generic or a comparison by the token before the `<`."""

    def __init__(self, text: str, jsx: bool) -> None:
        self.t, self.n, self.jsx = text, len(text), jsx
        self.out = list(text)
        self.depth = 0

    def blank(self, a: int, b: int) -> None:
        for k in range(a, min(b, self.n)):
            if self.out[k] != "\n":
                self.out[k] = " "

    def string(self, i: int) -> int:
        quote, j = self.t[i], i + 1
        while j < self.n:
            c = self.t[j]
            if c == "\\":
                j += 2
            elif c == quote:
                return j + 1
            elif c == "\n":
                return j                                   # an unterminated string ends with its line: never swallow the rest of the file
            else:
                j += 1
        return self.n

    def template(self, i: int) -> int:
        seg, j = i + 1, i + 1                              # the opening backtick stays
        while j < self.n:
            c = self.t[j]
            if c == "\\":
                j += 2
            elif c == "`":
                self.blank(seg, j)                           # the closing backtick stays
                return j + 1
            elif c == "$" and self.t[j + 1:j + 2] == "{":
                self.blank(seg, j + 2)
                k = self.code(j + 2, True)
                self.blank(k, k + 1)
                seg, j = k + 1, k + 1
            else:
                j += 1
        self.blank(seg, self.n)
        return self.n

    def regex(self, i: int) -> int:
        j, in_class = i + 1, False
        while j < self.n:
            c = self.t[j]
            if c == "\\":
                j += 2
                continue
            if c == "\n":
                return i + 1                               # not a regular expression: a division
            if in_class:
                in_class = c != "]"
            elif c == "[":
                in_class = True
            elif c == "/":
                j += 1
                while j < self.n and self.t[j].isalpha():
                    j += 1
                self.blank(i, j)
                return j
            j += 1
        return i + 1

    def jsx_ok(self, i: int, prev_char: str, prev_word: str) -> bool:
        if not self.jsx or not (prev_char in "" or prev_char in "(,=:[!&|?{};>" or prev_word in ("return", "default", "yield")):
            return False
        m = _IDENT.match(self.t, i + 1)
        if self.t[i + 1:i + 2] == ">":
            return True                                    # a fragment
        return bool(m) and self.t[m.end():m.end() + 1] not in (",",) and not self.t[m.end():].lstrip().startswith("extends ")

    def element(self, i: int) -> int:
        """A JSX element or fragment starting at `<`: tag, attributes, children, closing tag. Expressions in braces are code; text and strings are blanked."""
        self.depth += 1
        if self.depth > 200:
            raise RecursionError
        try:
            j = i + 1
            while j < self.n and self.t[j] != ">" and not self.t.startswith("/>", j):     # the tag name, then the attributes
                c = self.t[j]
                if c in "\"'":
                    k = self.string(j)
                    self.blank(j, k)
                    j = k
                elif c == "{":
                    k = self.code(j + 1, True)
                    j = k + 1
                elif self.t.startswith("//", j):
                    k = self.t.find("\n", j)
                    k = self.n if k < 0 else k
                    self.blank(j, k)
                    j = k
                elif self.t.startswith("/*", j):
                    k = self.t.find("*/", j + 2)
                    k = self.n if k < 0 else k + 2
                    self.blank(j, k)
                    j = k
                else:
                    j += 1
            if self.t[j:j + 2] == "/>":
                return j + 2
            j += 1                                          # past `>`: the children
            while j < self.n:
                k = j
                while k < self.n and self.t[k] not in "<{":
                    k += 1
                self.blank(j, k)
                if k >= self.n:
                    return self.n
                if self.t[k] == "{":
                    j = self.code(k + 1, True) + 1
                elif self.t[k + 1:k + 2] == "/":
                    e = self.t.find(">", k)
                    return self.n if e < 0 else e + 1
                else:
                    j = self.element(k)
            return self.n
        finally:
            self.depth -= 1

    def code(self, i: int, stop_at_brace: bool) -> int:
        """Scan code from `i`; with `stop_at_brace`, return the index of the `}` that closes the expression the scan started inside."""
        t, n, depth = self.t, self.n, 0
        prev_char, prev_word = "", ""
        while i < n:
            c = t[i]
            if c in " \t\r\n":
                i += 1
            elif t.startswith("//", i):
                j = t.find("\n", i)
                j = n if j < 0 else j
                self.blank(i, j)
                i = j
            elif t.startswith("/*", i):
                j = t.find("*/", i + 2)
                j = n if j < 0 else j + 2
                self.blank(i, j)
                i = j
            elif c in "\"'":
                j = self.string(i)
                self.blank(i + 1, j - 1 if j - 1 > i and t[j - 1] == c else j)        # the quotes stay, as the mark of a literal (a return type `"week" {`)
                i, prev_char, prev_word = j, '"', ""
            elif c == "`":
                i, prev_char, prev_word = self.template(i), "`", ""
            elif c == "/" and (prev_char == "" or prev_char in "(,=:[!&|?{};+-*%<>~^" or prev_word in _REGEX_AFTER_WORD):
                j = self.regex(i)
                prev_char, prev_word = ("/", "") if j == i + 1 else ('"', "")
                i = j
            elif c == "<" and self.jsx_ok(i, prev_char, prev_word):
                i, prev_char, prev_word = self.element(i), ">", ""
            elif c == "{":
                depth += 1
                i, prev_char, prev_word = i + 1, c, ""
            elif c == "}":
                if depth == 0 and stop_at_brace:
                    return i
                depth -= 1
                i, prev_char, prev_word = i + 1, c, ""
            elif c.isalnum() or c in "_$":
                m = _IDENT.match(t, i)
                j = m.end() if m else i + 1
                prev_char, prev_word = t[j - 1], (t[i:j] if m else "")
                i = j
            else:
                i, prev_char, prev_word = i + 1, c, ""
        return n

    def run(self) -> str:
        self.code(0, False)
        return "".join(self.out)


def mask_code(source: str, jsx: bool = False) -> str:
    """`source` with comments, strings, template text, regular-expression literals and JSX text blanked (see `_Masker`); the source itself when it
    cannot be followed (nested too deeply): the old behaviour, a plain brace count."""
    try:
        return _Masker(source, jsx).run()
    except RecursionError:
        return source


def _matching_brace_end(text: str, open_brace_pos: int) -> int:
    """Index just past the closing brace matching the `{` at open_brace_pos,
    via depth counting on text that `mask_code` has already blanked of strings,
    comments, regular expressions and JSX text. Unbalanced input (a parse this
    heuristic can't follow) falls back to "rest of file" rather than raising."""
    depth = 0
    for i in range(open_brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _expr_body_end(text: str, start: int, container_end: int) -> int:
    """End of a single-expression arrow body (no `{...}` block) -- the
    first top-level `,` before the enclosing object literal's own closing
    brace, tracking paren/bracket/brace depth so a call's own commas
    (`get<T>(a, b)`) don't end the body early. Not string/template-literal
    aware, same class of imprecision `_matching_brace_end` already
    accepts."""
    depth = 0
    i = start
    while i < container_end:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        i += 1
    return container_end


def _paren_end(masked: str, open_i: int) -> int:
    """Index just past the `)` matching the `(` at `open_i`, on masked text; the end of the text when unbalanced."""
    depth = 0
    for k in range(open_i, len(masked)):
        if masked[k] == "(":
            depth += 1
        elif masked[k] == ")":
            depth -= 1
            if depth == 0:
                return k + 1
    return len(masked)


def _statement_end(masked: str, i: int) -> int:
    """Index just past the `;` that ends the statement starting at `i` (at bracket depth 0), or where the enclosing block closes, or the end of the text."""
    depth = 0
    for k in range(i, len(masked)):
        c = masked[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return k
            depth -= 1
        elif c == ";" and depth == 0:
            return k + 1
    return len(masked)


def _angle_end(masked: str, i: int) -> int:
    """Index just past the `>` closing the type-parameter list that opens at `i` (`<T extends { a: number }>`); `=>` does not close it."""
    depth = 0
    for k in range(i, len(masked)):
        c = masked[k]
        if c == "<":
            depth += 1
        elif c == ">" and masked[k - 1] != "=":
            depth -= 1
            if depth == 0:
                return k + 1
        elif c in ";" and depth <= 1:
            return i                                            # not a type-parameter list
    return i


def _body_brace(masked: str, i: int) -> int:
    """The `{` that opens the body of a function or class whose signature runs up to `i`: the first `{` that is not a type literal (one that follows `:`,
    `|`, `&`, `<`, `,`, `(` or `=`, as in `): { a: number } {` or `extends B<{ x: 1 }> {`), which is skipped whole. -1 when a `;` comes first (a
    signature with no body: an overload or a declaration)."""
    prev = ""
    while i < len(masked):
        c = masked[i]
        if c in " \t\r\n":
            i += 1
        elif c == "{":
            if prev in (":", "|", "&", "<", ",", "(", "="):
                i, prev = _matching_brace_end(masked, i), "}"
            else:
                return i
        elif c == ";":
            return -1
        else:
            prev = c
            i += 1
    return -1


def _find_symbols(source: str, jsx: bool = False) -> list[tuple[str, str, int, int, int, int]]:
    """[(name, kind, line_start, line_end, body_start, body_end), ...] -- the lines are those of the declaration and of its closing token (#418);
    body_start/end bound the text a call-scan should search within for THIS symbol only, not the whole file (the same function-body scoping BL-4
    already established for precision over recall). Found on text with comments, strings, regular expressions and JSX text blanked (`mask_code`), so
    a brace or a declaration inside one of them does not count."""
    masked = mask_code(source, jsx)
    line = lambda pos: masked.count("\n", 0, pos) + 1
    out: list[tuple[str, str, int, int, int, int]] = []
    for pat, kind in ((_FUNC_DECL_RE, "function"), (_ARROW_CONST_RE, "function"), (_CLASS_RE, "class")):
        for m in pat.finditer(masked):
            name = m.group(1)
            if pat is _ARROW_CONST_RE:
                open_brace = m.end() - 1
                head = _ARROW_HEAD_RE.match(masked, m.start())
                if head:
                    params_end = _paren_end(masked, head.end() - 1)
                    tail = _ARROW_TAIL_RE.match(masked, params_end)
                    if params_end > open_brace and tail:           # the brace found is inside the parameters: the real body follows them
                        open_brace = tail.end() - 1
                    elif params_end > open_brace:                  # ... and none follows: an expression body (`=> confirm({ ... });`)
                        arrow = _ARROW_EXPR_RE.match(masked, params_end)
                        if arrow:
                            stmt_end = _statement_end(masked, arrow.end())
                            last = len(masked[:stmt_end].rstrip()) - 1
                            out.append((name, kind, line(m.start(1)), line(last), arrow.end(), stmt_end))
                            continue
            elif pat is _FUNC_DECL_RE:
                open_brace = _body_brace(masked, _paren_end(masked, m.end() - 1))
            else:
                after = m.end()
                while after < len(masked) and masked[after] in " \t\r\n":
                    after += 1
                if masked[after:after + 1] == "<":                 # `class Counter<T extends { a: number }> extends B<{ x: 1 }> {`
                    after = _angle_end(masked, after)
                open_brace = _body_brace(masked, after)
            if open_brace == -1:
                continue
            body_end = _matching_brace_end(masked, open_brace)
            out.append((name, kind, line(m.start(1)), line(body_end - 1), m.end(), body_end))

    # Object-literal methods (`export const pmsApi = { overview: () =>
    # get<T>("/overview"), ... }`) -- the real, dominant shape both real
    # frontends this was built for actually use (see module docstring).
    # Qualified by the outer container's own name, e.g. "pmsApi.overview" --
    # entries in a container nested deeper than one level flatten onto the
    # outermost container's name, an accepted approximation, not a full
    # recursive object-literal parser.
    for lit_m in _OBJECT_LITERAL_RE.finditer(masked):
        container_name = lit_m.group(1)
        open_brace = masked.find("{", lit_m.end() - 1)
        if open_brace == -1:
            continue
        container_end = _matching_brace_end(masked, open_brace)
        for em in _OBJECT_METHOD_RE.finditer(masked, open_brace, container_end):
            entry_name = em.group(1)
            body_start = em.end()
            if body_start < len(masked) and masked[body_start] == "{":
                body_end = _matching_brace_end(masked, body_start)
                last = body_end - 1
            else:
                body_end = _expr_body_end(masked, body_start, container_end)
                last = len(masked[:body_end].rstrip()) - 1          # the expression's last token, not the comma after it
            out.append((f"{container_name}.{entry_name}", "function", line(em.start(1)), line(max(last, body_start)), body_start, body_end))
    return out


def extract_file_calls(body: str, consts: dict[str, str], builders: dict[str, str], wrappers: dict[str, str]) -> list[tuple[str, str]]:
    """(method, normalised path) for each API call in a symbol's body (ODSF-314 shapes)."""
    out: list[tuple[str, str]] = []
    for _q, url, tail in _FETCH_LITERAL.findall(body):
        norm = normalise_path(url, consts)
        if norm:
            out.append((_method(tail), norm))
    for name, tail in _FETCH_BUILDER.findall(body):
        if name in builders:
            out.append((_method(tail), builders[name]))
    for name, prefix in wrappers.items():
        for m in re.finditer(r"\b" + re.escape(name) + r"(?:<[^>]*>)?\(\s*([`\"'])(.+?)\1(.{0,240})", body, re.S):
            norm = normalise_path(m.group(2), consts)
            if norm:
                out.append((_method(m.group(3)), prefix + norm))
    return out


def extract_file(path: Path, repo_root: Path, helpers: tuple[dict[str, str], dict[str, str]] | None = None,
                 ) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Returns (symbols, route_calls) for one .ts/.tsx file.
    symbols: [{qualified_name (bare name, no nesting -- top-level only),
               kind, line_start, line_end}, ...]
    route_calls: [(symbol_qualified_name, method, path), ...] -- the
    frontend half of BL-4b; build_symbols.py resolves these against real
    backend Symbol routes, this function has no visibility into those."""
    try:
        source = path.read_text(errors="replace")
    except OSError:
        return [], []

    consts = dict(CONST_STR_RE.findall(source))
    default_base_match = DEFAULT_BASE_PARAM_RE.search(source)
    default_base = consts.get(default_base_match.group(1), "") if default_base_match else ""

    symbols: list[dict] = []
    route_calls: list[tuple[str, str, str]] = []
    for name, kind, line_start, line_end, body_start, body_end in _find_symbols(source, path.suffix.lower() in (".tsx", ".jsx")):
        symbols.append({"qualified_name": name, "kind": kind, "line_start": line_start, "line_end": line_end})

        body = source[body_start:body_end]
        for m in CALL_RE.finditer(body):
            helper, call_path, rest = m.group(1), m.group(2), m.group(3)
            if call_path.startswith("$") or "{" in call_path:
                # ODSF-314: a template path is still a route, with its interpolations as parameter slots
                norm = normalise_path(call_path, consts)
                if norm:
                    route_calls.append((name, _METHOD_MAP[helper], norm))
                continue
            trailing_quoted = QUOTED_RE.findall(rest)
            explicit_base = trailing_quoted[-1] if trailing_quoted else None
            base = explicit_base if explicit_base is not None else default_base
            route_calls.append((name, _METHOD_MAP[helper], f"{base}{call_path}"))
        builders, wrappers = helpers or ({}, {})
        for method, call_path in extract_file_calls(body, consts, builders, wrappers):
            route_calls.append((name, method, call_path))
    return symbols, route_calls


def list_ts_files(repo_root: Path) -> list[Path]:
    return sorted(
        p for p in repo_root.rglob("*")
        if p.suffix in (".ts", ".tsx")
        and "node_modules" not in p.parts and ".next" not in p.parts and p.name.endswith((".ts", ".tsx"))
        and not p.name.endswith(".d.ts")
    )
