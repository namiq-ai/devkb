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


def _matching_brace_end(text: str, open_brace_pos: int) -> int:
    """Index just past the closing brace matching the `{` at open_brace_pos,
    via depth counting -- not string/comment-aware (a `{` inside a string
    literal or comment can throw this off), the same class of imprecision
    discovery/extract_typescript.py's own regex approach already accepts.
    Unbalanced input (a parse this heuristic can't follow) falls back to
    "rest of file" rather than raising."""
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


def _find_symbols(source: str) -> list[tuple[str, str, int, int, int]]:
    """[(name, kind, line_start, body_start, body_end), ...] -- body_start/
    end bound the text a call-scan should search within for THIS symbol
    only, not the whole file (the same function-body scoping BL-4 already
    established for precision over recall)."""
    out: list[tuple[str, str, int, int, int]] = []
    for pat, kind in ((_FUNC_DECL_RE, "function"), (_ARROW_CONST_RE, "function"), (_CLASS_RE, "class")):
        for m in pat.finditer(source):
            name = m.group(1)
            open_brace = source.find("{", m.end() - 1)
            if open_brace == -1:
                continue
            body_end = _matching_brace_end(source, open_brace)
            line_start = source.count("\n", 0, m.start()) + 1
            out.append((name, kind, line_start, m.end(), body_end))

    # Object-literal methods (`export const pmsApi = { overview: () =>
    # get<T>("/overview"), ... }`) -- the real, dominant shape both real
    # frontends this was built for actually use (see module docstring).
    # Qualified by the outer container's own name, e.g. "pmsApi.overview" --
    # entries in a container nested deeper than one level flatten onto the
    # outermost container's name, an accepted approximation, not a full
    # recursive object-literal parser.
    for lit_m in _OBJECT_LITERAL_RE.finditer(source):
        container_name = lit_m.group(1)
        open_brace = source.find("{", lit_m.end() - 1)
        if open_brace == -1:
            continue
        container_end = _matching_brace_end(source, open_brace)
        for em in _OBJECT_METHOD_RE.finditer(source, open_brace, container_end):
            entry_name = em.group(1)
            line_start = source.count("\n", 0, em.start()) + 1
            body_start = em.end()
            if body_start < len(source) and source[body_start] == "{":
                body_end = _matching_brace_end(source, body_start)
            else:
                body_end = _expr_body_end(source, body_start, container_end)
            out.append((f"{container_name}.{entry_name}", "function", line_start, body_start, body_end))
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
               kind, line_start}, ...]
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
    for name, kind, line_start, body_start, body_end in _find_symbols(source):
        symbols.append({"qualified_name": name, "kind": kind, "line_start": line_start})

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
