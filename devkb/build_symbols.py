#!/usr/bin/env python3
"""devkb Symbol-graph refresh (BL-3/BL-3b/BL-3c/BL-4b, body/legs model) --
standalone, NOT part of devkb/build.py's regular run.

Usage: python3 devkb/build_symbols.py --project CODE

Extracts function/class/method-level `Symbol` nodes from every git-tracked
Python AND TypeScript/TSX file -- the "as-built design" layer the body/legs
model calls for -- plus:
  - BL-3b: cross-file CALLS resolution for Python (same-file first, then
    via a file's own imports to another file's symbol) -- widened from the
    original same-file-only scope specifically because this build is
    already decoupled from devkb/build.py's hot path (the same reasoning
    that justified the decoupling in the first place: pay real analysis
    cost once, on an explicit refresh, not never).
  - BL-3c: TypeScript/TSX Symbol extraction (devkb/ts_symbols.py) -- devkb
    was Python-only until now, meaning 0 of any registered project's real
    frontend code -- the actual user-facing behavior -- was in the graph.
  - BL-4b: backend FastAPI route capture (ported from discovery/
    extract_python.py's own _decorator_route/_router_prefix) plus a
    cross-language CALLS_API edge resolving a frontend Symbol's own
    get/post/put(...) call site to the real backend Symbol that handles
    it -- the literal "UI action -> backend code" connective tissue a bug
    trace / sequence analysis / user-journey audit actually needs.

Deliberately decoupled from the regular fast build: a standalone extractor with its own persisted
artifact, read by multiple consumers rather than re-derived by each one.
Writes `.devkb/symbols-{nodes,edges,manifest}.jsonl`. devkb/build.py's own
regular run reads these (if present) and merges them into the main store;
it never regenerates them. Re-run this script explicitly whenever the
Symbol graph needs to catch up with real source changes -- its own
manifest's git_head/built_at make that staleness checkable instead of
silent, the gap confirmed live in discovery/graph.json (no such fields at
all) and deliberately not repeated here.
"""
from __future__ import annotations

import argparse
import ast
import re
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb import cpp_graph, csharp_symbols, ts_symbols  # noqa: E402
from devkb.extractors.tickets_git import _run  # noqa: E402
from devkb.gitutil import git_head  # noqa: E402
from devkb.model import DevKBGraph  # noqa: E402
from devkb.project_context import ProjectContext, resolve  # noqa: E402

# ── FastAPI route capture, ported from discovery/extract_python.py's own
# _decorator_route/_router_prefix (BL-4b) -- same regex/AST logic, not a
# reinvention, so a route this repo's own discovery/ already resolves
# resolves the same way here. ──────────────────────────────────────────────
_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
_ROUTER_NAMES = {"router", "app"}
# Routers are often named for what they serve (`public_router`, `user_router`, `admin_app`) or by framework habit
# (`api`, `bp`): the truth generator accepted any receiver and the graph accepted two names, so a whole router's
# handlers were invisible. The decorator must still carry a string path, which keeps `cache.get(...)` out.
_ROUTER_NAME = re.compile(r"(?:^|_)(?:router|app|api|bp|blueprint)$", re.IGNORECASE)


def _odoo_route(dec: ast.expr) -> tuple[str, str] | None:
    """`@http.route('/path', methods=['POST'], ...)` (ODSF-304). Odoo's own
    controller decorator, which the FastAPI-shaped matcher below never saw, so
    one project's 143 routes were reported as 0. A list of paths or methods
    yields the first of each: one handler is one Endpoint here, and the extra
    aliases are the same code."""
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "route" and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "http"):
        return None
    first: ast.expr | None = dec.args[0] if dec.args else next(
        (kw.value for kw in dec.keywords if kw.arg == "route"), None)
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        first = first.elts[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    method = "ANY"
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)) and kw.value.elts:
            head = kw.value.elts[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                method = head.value.upper()
    return method, first.value


def _decorator_route(dec: ast.expr) -> tuple[str, str] | None:
    odoo = _odoo_route(dec)
    if odoo is not None:
        return odoo
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    if dec.func.attr not in _HTTP_METHODS:
        return None
    if not isinstance(dec.func.value, ast.Name) or not (dec.func.value.id in _ROUTER_NAMES or _ROUTER_NAME.search(dec.func.value.id)):
        return None
    if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
        return None
    return dec.func.attr.upper(), dec.args[0].value


def _router_prefix(tree: ast.Module) -> str:
    """The prefix a module's router declares. Any constructor named like a router counts (`APIRouter`,
    `fastapi.APIRouter`, a project's own `PrefectRouter`), and Flask's `Blueprint(url_prefix=...)`: reading only
    `APIRouter` left a project's prefixes empty, so `POST /` in five modules collapsed into one Endpoint."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if not (name.endswith("Router") or name == "Blueprint"):
            continue
        for kw in node.keywords:
            if kw.arg in ("prefix", "url_prefix") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return ""


def _list_python_files(repo_root: Path) -> list[str]:
    # git ls-files (not rglob) so this automatically respects .gitignore --
    # no manual __pycache__/venv exclusion list to keep in sync by hand.
    out = _run(["git", "ls-files", "--recurse-submodules", "--", "*.py"], repo_root)
    return [f for f in out.splitlines() if f.strip()]


# Third-party and generated JavaScript is not the project's own behaviour.
_JS_SKIP = re.compile(
    r"(\.min\.js$|\.test\.[cm]?js$|\.spec\.[cm]?js$|(^|/)(vendor|node_modules|output|dist|build)/)")
# ODSF-314: `lib/` holds vendored code only as compiled JavaScript; a project's own TypeScript lives there too
# (OCO's webapp/frontend/src/lib/api.ts is its whole API layer), so `lib/` is skipped for .js/.mjs only.
_JS_LIB = re.compile(r"(^|/)(lib|libs)/[^/].*\.m?js$")


def _list_ts_files(repo_root: Path) -> list[str]:
    out = _run(["git", "ls-files", "--recurse-submodules", "--", "*.ts", "*.tsx", "*.js", "*.mjs"], repo_root)
    return [
        f for f in out.splitlines()
        if f.strip() and not f.endswith(".d.ts") and not _JS_SKIP.search(f) and not _JS_LIB.search(f)
    ]


# ODSF-304: an Odoo addon's behaviour lives in XML as much as in Python, and
# none of it had a node. Only the declarations a person uses or navigates by.
_XML_TAG = re.compile(r"<(template|record|menuitem|t)\b([^>]*)>", re.IGNORECASE)
_XML_ATTR = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_XML_RECORD_KINDS = {"ir.ui.view": "view", "ir.cron": "cron", "res.groups": "group"}


def _odoo_xml_symbols(repo_root: Path) -> dict[str, list[dict]]:
    """{file: [{qualified_name, kind, line_start}, ...]} for QWeb templates,
    views, actions, menus, cron jobs and security groups declared in tracked
    XML. Regex over the tag, not a full parse: Odoo data files carry
    `t-` attributes and entities that make a strict parser reject real files."""
    out: dict[str, list[dict]] = {}
    for rel in _run(["git", "ls-files", "--recurse-submodules", "--", "*.xml"], repo_root).splitlines():
        if not rel.strip():
            continue
        try:
            text = (repo_root / rel).read_text(errors="replace")
        except OSError:
            continue
        found: list[dict] = []
        for match in _XML_TAG.finditer(text):
            tag = match.group(1).lower()
            attrs = {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3))
                     for m in _XML_ATTR.finditer(match.group(2))}
            line = text.count("\n", 0, match.start()) + 1
            if tag == "template" and attrs.get("id"):
                found.append({"qualified_name": attrs["id"], "kind": "qweb_template", "line_start": line})
            elif tag == "menuitem" and attrs.get("id"):
                found.append({"qualified_name": attrs["id"], "kind": "menu", "line_start": line})
            elif tag == "t" and attrs.get("t-name"):
                found.append({"qualified_name": attrs["t-name"], "kind": "qweb_template", "line_start": line})
            elif tag == "record" and attrs.get("id") and attrs.get("model"):
                model_name = attrs["model"]
                kind = _XML_RECORD_KINDS.get(model_name) or (
                    "action" if model_name.startswith("ir.actions.") else None)
                if kind:
                    found.append({"qualified_name": attrs["id"], "kind": kind, "line_start": line})
        if found:
            out[rel] = found
    return out


def _first_line(docstring: str | None) -> str | None:
    if not docstring:
        return None
    return docstring.strip().splitlines()[0].strip()


EXPR = "<expr>"


def _call_name(func: ast.expr) -> tuple[str | None, str] | None:
    """(receiver_name_or_None, short_name) for a call target. The receiver
    is used for BL-3b's cross-file resolution (module.func() -> follow
    `module`'s own import to the right file); same-file/global fallback
    still works from the short name alone when there's no usable receiver
    (a bare `func()`, or a call on something more complex than a plain
    name, e.g. `get_thing().run()`)."""
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        # A call on an expression (`Path(p).resolve()`, `super().setUp()`) has a receiver, just not a name: EXPR,
        # never None, so it is not mistaken for a bare call to a same-named function of this file.
        receiver = func.value.id if isinstance(func.value, ast.Name) else _dotted(func.value) or EXPR
        return receiver, func.attr
    return None


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for an attribute chain rooted at a plain name (`prefect.context` in `prefect.context.get_run_context()`,
    after `import prefect.context`), else None. Resolved only when its root is an imported module; any other chain
    (`self._store`, `request.app`) is treated as an expression, as before."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if isinstance(node, ast.Name) and parts and node.id not in ("self", "cls"):
        return ".".join([node.id, *parts])
    return None


def _calls_in_body(node: ast.AST) -> list[tuple[str | None, str]]:
    """(receiver, short_name) calls made directly within node's own body --
    explicitly NOT descending into a nested function/class def's body, so a
    nested def's own calls get attributed to ITS symbol when the visitor
    reaches it, not double-counted here."""
    calls: list[tuple[str | None, str]] = []

    def walk(n: ast.AST, top: bool) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not top:
                continue
            if isinstance(child, ast.Call):
                hit = _call_name(child.func)
                if hit:
                    calls.append(hit)
            walk(child, top=False)

    walk(node, top=True)
    return calls


# A call made when the module is imported (`app_dirs = get_app_dirs()`), or in a class body, outside every function.
# It has no Symbol to start a CALLS edge from (Symbol is a function, class or method), so it is resolved like any call
# and recorded on the called Symbol as `module_callers`: the files a signature change breaks.
MODULE_CALLER = "<module>"


def _bound_names(fn: ast.AST) -> set[str]:
    """Names a function binds itself (parameters, assignments, loop and comprehension targets, local imports), not
    looking into nested defs: a load of one of these is the local, never a module-level function of that name."""
    a = fn.args
    out = {x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg) if x is not None}
    for n in _own_body(fn):
        if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update((al.asname or al.name).split(".")[0] for al in n.names)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
    return out


def _value_refs(tree: ast.Module) -> list[tuple[str, str | None, str, int]]:
    """(scope, receiver, name, line) for every name that may be a function used as a value, not called:
    `pool.submit(self._moved_files, rev)`, `sorted(xs, key=key_of)`, a dispatch table. receiver is "self"/"cls" for
    `self.name`, None for a bare name; scope is the enclosing function's qualified name, or MODULE_CALLER. Extract
    resolves them; a resolved one is a reference, not a call: who calls through it is not visible (#69)."""
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    attr_of = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}  # `f.__name__`, `self._store.get`
    out: list[tuple[str, str | None, str, int]] = []

    def visit(n: ast.AST, scope: list[str], bound: set[str]) -> None:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            head = [*n.decorator_list, *getattr(n, "bases", ()), *getattr(n, "keywords", ())]
            if not isinstance(n, ast.ClassDef):
                head += [*n.args.defaults, *(d for d in n.args.kw_defaults if d is not None)]
            for h in head:                              # evaluated in the enclosing scope
                visit(h, scope, bound)
            inner = bound if isinstance(n, ast.ClassDef) else bound | _bound_names(n)
            for b in n.body:
                visit(b, [*scope, n.name], inner)
            return
        if id(n) not in called and id(n) not in attr_of and isinstance(getattr(n, "ctx", None), ast.Load):
            where = ".".join(scope) or MODULE_CALLER
            if isinstance(n, ast.Name) and n.id not in bound:
                out.append((where, None, n.id, n.lineno))
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ("self", "cls"):
                out.append((where, n.value.id, n.attr, n.lineno))
        for c in ast.iter_child_nodes(n):
            visit(c, scope, bound)

    visit(tree, [], set())
    return out


def _module_level_calls(tree: ast.Module) -> list[tuple[str | None, str]]:
    calls: list[tuple[str | None, str]] = []

    def walk(n: ast.AST) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                hit = _call_name(child.func)
                if hit:
                    calls.append(hit)
            walk(child)

    walk(tree)
    return calls


def _imports(tree: ast.AST) -> list[tuple[str, str | None]]:
    """[(local_name, dotted_module_or_None), ...] -- dotted_module is None
    for a bare `import X` (X itself is the module, not a from-import of a
    specific name from it). Shared with extractors/symbol_tests.py (BL-4),
    which does the same "resolve an imported name to a Symbol" job for
    test files -- one implementation, not two copies to keep in sync."""
    out: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out.append((alias.asname or alias.name, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.asname or alias.name.split(".")[0], None))
    return out


def _module_paths(dotted: str) -> list[str]:
    slash = dotted.replace(".", "/")
    return [f"{slash}.py", f"{slash}/__init__.py"]


def _import_descriptors(tree: ast.AST) -> list[tuple[int, str, str | None, str]]:
    """[(level, module, name_or_None, local_name), ...] -- every import with
    what `_imports` throws away (ODSF-305): the module an alias stands for,
    the imported name, and the relative level. `import a.b as m` is
    (0, "a.b", None, "m"); `from a import b as c` is (0, "a", "b", "c");
    `from . import x` is (1, "", "x", "x")."""
    out: list[tuple[int, str, str | None, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    out.append((node.level or 0, node.module or "", alias.name, alias.asname or alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out.append((0, alias.name, None, alias.asname))
                else:
                    top = alias.name.split(".")[0]
                    out.append((0, top, None, top))
    return out


def _import_targets(
    descriptors: list[tuple[int, str, str | None, str]], rel_path: str,
) -> tuple[dict[str, list[str]], dict[str, tuple[str, str]]]:
    """(receiver_modules, bare_symbols) for one file (ODSF-305).

    receiver_modules[local] lists the dotted modules `local` may be, so a call
    `local.func()` is looked up in each. `from pkg import mod` makes `mod` a
    module `pkg.mod` -- the case the old resolver got wrong by searching
    `pkg` itself. bare_symbols[local] = (module, original_name) for a bare
    call `local()` made through `from module import original_name as local`.
    Relative imports are anchored on the caller's own directory."""
    here = rel_path.split("/")[:-1]
    receivers: dict[str, list[str]] = {}
    bare: dict[str, tuple[str, str]] = {}
    for level, module, name, local in descriptors:
        if level:
            keep = here[: len(here) - (level - 1)] if level - 1 <= len(here) else []
            base = ".".join(keep + ([module] if module else []))
        else:
            base = module
        if not base and name is None:
            continue
        if name is None:
            receivers.setdefault(local, []).append(base)
        else:
            receivers.setdefault(local, []).append(f"{base}.{name}" if base else name)
            if base:
                bare[local] = (base, name)
    return receivers, bare


def _py_literals(tree: ast.AST) -> list[str]:
    """String constants that look like a Python file path in this file (ODSF-305):
    `.../dev-orchestrator.py`, the way a test names a module it loads with
    importlib because the file name is not a valid module name."""
    return sorted({
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.endswith(".py") and len(n.value) < 200 and "\n" not in n.value
    })


_SUFFIX_CACHE: dict[int, tuple[int, dict[str, list[str]]]] = {}
_LEADING_STEPS = re.compile(r"^(?:\.{1,2}/|/)+")  # leading `./`, `../` and `/`: path steps, not characters


def _suffix_index(per_file_symbols: dict[str, list[dict]]) -> dict[str, list[str]]:
    """Every trailing path of every file -> the files that end that way
    (`a/b/c.py` is indexed as `c.py`, `b/c.py` and `a/b/c.py`). Built once per
    symbol table so module lookup stays a dict hit on a repo with thousands of
    files (ODSF-305)."""
    cached = _SUFFIX_CACHE.get(id(per_file_symbols))
    if cached and cached[0] == len(per_file_symbols):
        return cached[1]
    index: dict[str, list[str]] = {}
    for path in per_file_symbols:
        parts = path.split("/")
        for i in range(len(parts)):
            index.setdefault("/".join(parts[i:]), []).append(path)
    _SUFFIX_CACHE[id(per_file_symbols)] = (len(per_file_symbols), index)
    return index


def _resolve_via_literals(
    literals: list[str], short_name: str, per_file_symbols: dict[str, list[dict]],
) -> str | None:
    """`short_name` in the one file this caller names by path, when exactly one
    symbol matches across every file those path strings point at."""
    index = _suffix_index(per_file_symbols)
    files = {p for lit in literals for p in index.get(_LEADING_STEPS.sub("", lit), [])}  # keeps `.github/` (#86)
    hits = [f"{f}::{s['qualified_name']}" for f in sorted(files) for s in per_file_symbols[f]
            if s["qualified_name"].rsplit(".", 1)[-1] == short_name]
    return hits[0] if len(hits) == 1 else None


# Re-exports: file -> {name it makes importable: (dotted module it imported that name from, original name)}, so
# `from pkg import f` resolves when `pkg/__init__.py` holds `from .impl import f`. Registered per symbol table (the
# table object itself is kept, so a reused id() can never pick up another build's map).
_REEXPORTS: dict[int, tuple[dict, dict[str, dict[str, tuple[str, str]]]]] = {}


def register_reexports(per_file_symbols: dict[str, list[dict]], reexports: dict[str, dict[str, tuple[str, str]]]) -> None:
    _REEXPORTS[id(per_file_symbols)] = (per_file_symbols, reexports)


def collect_reexports(repo_root: Path, rel_paths: list[str]) -> dict[str, dict[str, tuple[str, str]]]:
    """Every file's from-imports, as `_import_targets` resolves them (relative imports anchored on the file)."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for rel in rel_paths:
        try:
            tree = ast.parse((repo_root / rel).read_text(errors="replace"))
        except (SyntaxError, OSError, ValueError, RecursionError):
            continue
        bare = _import_targets(_import_descriptors(tree), rel)[1]
        if bare:
            out[rel] = bare
    return out


def _resolve_cross_file_symbol(
    dotted_module: str, caller_rel_path: str, short_name: str, per_file_symbols: dict[str, list[dict]],
    _depth: int = 0,
) -> str | None:
    """Resolves `dotted_module`'s `short_name` symbol to a real
    `path::qualified_name`, repo-root-relative first, then relative to
    each ancestor directory of the caller's own file, closest first --
    real per-service import convention this codebase actually uses
    (`from app.middleware.auth import AuthMiddleware` inside
    webapp/backend/ means webapp/backend/app/middleware/auth.py, not a
    repo-root-level app/; confirmed live, not a hypothetical). None when
    no candidate resolves to exactly one match -- skipped, not guessed."""
    entry = _REEXPORTS.get(id(per_file_symbols))
    reexports = entry[1] if entry and entry[0] is per_file_symbols else {}

    def _match(guess: str) -> str | None:
        hits = [s["qualified_name"] for s in per_file_symbols.get(guess) or []
                if s["qualified_name"].rsplit(".", 1)[-1] == short_name]
        if len(hits) == 1:
            return f"{guess}::{hits[0]}"
        if hits:
            return None
        # Not defined here: the module may re-export it (`from .wallets import get_wallet` in a package's
        # `__init__.py`). Follow that import, a bounded number of hops.
        via = reexports.get(guess, {}).get(short_name)
        if via and _depth < 6:
            return _resolve_cross_file_symbol(via[0], guess, via[1], per_file_symbols, _depth + 1)
        return None

    candidates = _module_paths(dotted_module)
    for guess in candidates:
        hit = _match(guess)
        if hit:
            return hit

    parts = caller_rel_path.split("/")[:-1]  # caller's own containing directories, deepest last
    for i in range(len(parts), 0, -1):
        prefix = "/".join(parts[:i])
        for guess in candidates:
            hit = _match(f"{prefix}/{guess}")
            if hit:
                return hit

    # ODSF-305: a module reached through a `sys.path.insert(...)` lives in a
    # directory no ancestor rule can guess (`import sdp_landing` -> sdp/orchestrator/).
    # Accept it only when exactly one tracked file ends with the module's path:
    # a unique MODULE name, never a unique symbol name, which was rejected above
    # because `get`/`run`/`main` resolve to the wrong file.
    index = _suffix_index(per_file_symbols)
    found = {p for guess in candidates for p in index.get(guess, [])}
    if len(found) == 1:
        return _match(next(iter(found)))
    return None


# ── ODSF-312: calls through an object whose class is known ──────────────────
# `self._store.add_edge(...)` and `store = RuntimeStore(); store.add_edge(...)` carry no module name, so the import
# resolver above never sees them; in OCO they were most of the calls into service classes. A receiver's class is
# taken only from what the code states: a parameter annotation (`store: RuntimeStore`, `Optional[...]`, `X | None`,
# a string annotation), a constructor call (`x = RuntimeStore(...)`, `with C(...) as x`, `x: C = ...`), a class-level
# annotation, or a `self.attr` set in any method of the class from one of those. Nothing is inferred from a return
# type or a factory, so a miss stays a miss rather than becoming a wrong edge.
def _annotation_class(ann: ast.expr | None) -> str | None:
    if ann is None:
        return None
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        try:
            ann = ast.parse(ann.value, mode="eval").body
        except SyntaxError:
            return None
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):  # X | None
        sides = [s for s in (ann.left, ann.right) if not (isinstance(s, ast.Constant) and s.value is None)]
        return _annotation_class(sides[0]) if len(sides) == 1 else None
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, (ast.Name, ast.Attribute)):
        outer = ann.value.id if isinstance(ann.value, ast.Name) else ann.value.attr
        return _annotation_class(ann.slice) if outer == "Optional" else None
    return _class_ref(ann)


def _looks_like_class(name: str) -> bool:
    """Capitalised after any leading underscores: `Index`, and a private `_Index` (dogfood D1, #40)."""
    return name.lstrip("_")[:1].isupper()


def _class_ref(node: ast.expr) -> str | None:
    """`Cls` or `module.Cls` when the name looks like a class (capitalised, private ones included), else None."""
    if isinstance(node, ast.Name) and _looks_like_class(node.id):
        return node.id
    if isinstance(node, ast.Attribute) and _looks_like_class(node.attr) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _constructed(value: ast.expr | None) -> str | None:
    return _class_ref(value.func) if isinstance(value, ast.Call) else None


def _own_body(node: ast.AST):
    """Nodes of a function's own body, not descending into nested defs or classes (as _calls_in_body)."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))


def _typed_calls(tree: ast.Module) -> list[tuple[str, str, str]]:
    """[(caller_qualname, class_ref, method)] for calls on a receiver whose class the code states."""
    out: list[tuple[str, str, str]] = []

    def params(fn) -> dict[str, str]:
        a = fn.args
        env = {}
        for p in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
            cls = _annotation_class(p.annotation)
            if cls:
                env[p.arg] = cls
        return env

    def attr_types(cls_node: ast.ClassDef) -> dict[str, str]:
        types: dict[str, str] = {}
        for stmt in cls_node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                cls = _annotation_class(stmt.annotation) or _constructed(stmt.value)
                if cls:
                    types[stmt.target.id] = cls
        for fn in cls_node.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            env = params(fn)
            for n in _own_body(fn):
                targets, value, ann = [], None, None
                if isinstance(n, ast.Assign):
                    targets, value = n.targets, n.value
                elif isinstance(n, ast.AnnAssign):
                    targets, value, ann = [n.target], n.value, n.annotation
                for t in targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        cls = (_annotation_class(ann) or _constructed(value)
                               or (env.get(value.id) if isinstance(value, ast.Name) else None))
                        if cls:
                            types.setdefault(t.attr, cls)
        return types

    def visit_function(fn, qual: str, self_types: dict[str, str], enclosing: str = "",
                       outer: dict[str, str] | None = None) -> dict[str, str]:
        # a nested function sees the names of the function around it (dogfood D7, #40: `index: _Index` used from a
        # helper defined inside the function), its own parameters shadowing them
        env = {**(outer or {}), **params(fn)}
        for n in _own_body(fn):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                cls = _constructed(n.value)
                if cls:
                    env[n.targets[0].id] = cls
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                cls = _annotation_class(n.annotation) or _constructed(n.value)
                if cls:
                    env[n.target.id] = cls
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for item in n.items:
                    cls = _constructed(item.context_expr)
                    if cls and isinstance(item.optional_vars, ast.Name):
                        env[item.optional_vars.id] = cls
        for n in _own_body(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            recv, method = n.func.value, n.func.attr
            cls = None
            if isinstance(recv, ast.Name) and recv.id in ("self", "cls") and enclosing:
                cls = "self:" + enclosing  # ODSF-313: resolved on the enclosing class, then its bases
            elif isinstance(recv, ast.Name):
                cls = env.get(recv.id) or (recv.id if _looks_like_class(recv.id) else None)  # `Cls.static()` too
            elif isinstance(recv, ast.Attribute) and isinstance(recv.value, ast.Name) and recv.value.id == "self":
                cls = self_types.get(recv.attr)
            elif isinstance(recv, ast.Call):
                cls = _constructed(recv)  # `RuntimeStore().add_edge(...)`, built and called in one expression
            if cls:
                out.append((qual, cls, method))
        return env

    def walk(node, stack: list[str], self_types: dict[str, str], cls_qual: str = "",
             outer: dict[str, str] | None = None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, stack + [child.name], attr_types(child), ".".join(stack + [child.name]))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join(stack + [child.name])
                env = visit_function(child, qual, self_types, cls_qual, outer)
                walk(child, stack + [child.name], {}, "", env)
            else:
                walk(child, stack, self_types, cls_qual, outer)

    walk(tree, [], {})
    return out


def _resolve_class(
    cls_ref: str, rel_path: str, per_file_symbols: dict[str, list[dict]],
    targets: tuple[dict[str, list[str]], dict[str, tuple[str, str]]],
) -> str | None:
    """`path::Cls` for a class named in `rel_path`: its own file, `from m import Cls`, or `m.Cls` with `import m`."""
    if cls_ref.startswith("self:"):
        return f"{rel_path}::{cls_ref[5:]}"
    receivers, bare = targets
    found: str | None = None
    if "." not in cls_ref and any(s["qualified_name"] == cls_ref for s in per_file_symbols.get(rel_path, [])):
        found = f"{rel_path}::{cls_ref}"
    elif "." not in cls_ref and cls_ref in bare:
        module, original = bare[cls_ref]
        found = _resolve_cross_file_symbol(module, rel_path, original, per_file_symbols)
    elif "." in cls_ref:
        alias, name = cls_ref.split(".", 1)
        for module in receivers.get(alias, []):
            found = _resolve_cross_file_symbol(module, rel_path, name, per_file_symbols)
            if found:
                break
    return found


def _resolve_typed_call(
    cls_ref: str, method: str, rel_path: str, per_file_symbols: dict[str, list[dict]],
    targets: tuple[dict[str, list[str]], dict[str, tuple[str, str]]],
    bases: dict[str, list[str]] | None = None,
) -> str | None:
    """`path::Cls.method` for a method called on an instance of `cls_ref`, or None. The method must be defined on the
    class or, through EXTENDS (ADR-SDP-DEVKB-006), on one of its bases, nearest first."""
    found = _resolve_class(cls_ref, rel_path, per_file_symbols, targets)
    seen: set[str] = set()
    queue = [found] if found else []
    while queue:
        cls_key = queue.pop(0)
        if cls_key in seen or len(seen) > 12:
            continue
        seen.add(cls_key)
        path, qual = cls_key.split("::", 1)
        wanted = f"{qual}.{method}"
        if any(s["qualified_name"] == wanted for s in per_file_symbols.get(path, [])):
            return f"{path}::{wanted}" + ("" if cls_key == found else "#base")
        queue.extend((bases or {}).get(cls_key, []))
    return None

# ── BL-9: RAISES/LOGS/complexity, all single-pass reads of the same tree
# already parsed for Symbol extraction -- zero new dependency. ─────────────
_LOG_LEVELS = {"error", "warning", "critical", "exception"}
_LOG_LEVEL_MAP = {"exception": "error"}  # .exception() logs at error level
_LOGGER_RECEIVERS = {"logger", "logging", "log"}


def _message_template(node: ast.expr) -> str | None:
    """A literal or f-string message, interpolated parts normalized to `{}`
    -- same "a message can be long/formatted" handling Warning's own hashing
    already established. None for anything else (a str.format() call, a
    computed value) -- not guessed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [str(v.value) if isinstance(v, ast.Constant) else "{}" for v in node.values]
        return "".join(parts)
    return None


def _exception_type_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _http_status_code(call: ast.Call) -> int | None:
    for kw in call.keywords:
        if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
            return kw.value.value
    return None  # a variable/expression status_code is skipped, not guessed


def _raises_in_body(node: ast.AST) -> list[tuple[str, str | None, int | None]]:
    """(exception_type, message_template, status_code) for each `raise
    Exc(...)` directly in node's own body -- same top-scoping as
    _calls_in_body, so a nested function's own raises attribute to ITS
    symbol, not this one."""
    out: list[tuple[str, str | None, int | None]] = []

    def walk(n: ast.AST, top: bool) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not top:
                continue
            if isinstance(child, ast.Raise) and child.exc is not None:
                exc_type = _exception_type_name(child.exc)
                if exc_type:
                    message = None
                    status_code = None
                    if isinstance(child.exc, ast.Call):
                        if child.exc.args:
                            message = _message_template(child.exc.args[0])
                        for kw in child.exc.keywords:
                            if kw.arg == "detail":  # HTTPException's own message kwarg
                                message = _message_template(kw.value) or message
                        status_code = _http_status_code(child.exc)
                    out.append((exc_type, message, status_code))
            walk(child, top=False)

    walk(node, top=True)
    return out


def _logs_in_body(node: ast.AST) -> list[tuple[str, str | None]]:
    """(level, message_template) for recognized logger.<level>(...) calls
    directly in node's own body -- allow-list receiver names, extensible
    the same way _HTTP_METHODS/_ROUTER_NAMES are."""
    out: list[tuple[str, str | None]] = []

    def walk(n: ast.AST, top: bool) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not top:
                continue
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr in _LOG_LEVELS
                    and isinstance(child.func.value, ast.Name) and child.func.value.id in _LOGGER_RECEIVERS):
                level = _LOG_LEVEL_MAP.get(child.func.attr, child.func.attr)
                message = _message_template(child.args[0]) if child.args else None
                out.append((level, message))
            walk(child, top=False)

    walk(node, top=True)
    return out


def _complexity(node: ast.AST) -> int:
    """Cheap branch-count proxy (KNOWLEDGE_SPEC.md Section 3), not a full
    cyclomatic-complexity library -- counts If/For/While/Try anywhere
    within node's own subtree, nested defs included (this is a structural
    size signal for the whole symbol, not a body-scoped call/raise list)."""
    return sum(1 for child in ast.walk(node) if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)))


def _error_signature_key(kind: str, label: str, message_template: str | None) -> str:
    import hashlib
    basis = f"{kind}:{label}:{message_template or ''}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


# ── BL-10: middleware registration -- a distinct pattern from a direct
# CALLS edge (registration, not invocation), same rationale as BL-4b's
# route capture. ────────────────────────────────────────────────────────
def _middleware_registrations(tree: ast.Module) -> list[tuple[str, str]]:
    """(middleware_short_name, receiver) for each `<app_or_router>.
    add_middleware(X, ...)` call anywhere in the file."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_middleware"):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id in _ROUTER_NAMES):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        name = arg.id if isinstance(arg, ast.Name) else (arg.attr if isinstance(arg, ast.Attribute) else None)
        if name:
            out.append((name, node.func.value.id))
    return out


# ── BL-12: daemon-entry touch-point detection (KNOWLEDGE_SPEC.md Section
# 4a) -- the one touch-point kind nothing else already captures (`scheduled`
# reads Symbol.decorators, already extracted; `ui_handler`/`endpoint` are
# derivable from graph structure alone). Extensible, not exhaustive, same
# framing as the spec's own "new kinds get added as new patterns are
# found" note. ──────────────────────────────────────────────────────────
def _daemon_entries(tree: ast.Module) -> list[str]:
    """Short names of same-file symbols invoked as a process/thread entry
    point: `if __name__ == "__main__": <call>()`, or `target=` to
    `Thread(...)`/passed to `asyncio.create_task(...)`. Same-file
    resolution only -- these patterns overwhelmingly target a local
    function in real code, and a cross-file guess here risks a false
    touch point more than a missed one is worth."""
    out: list[str] = []

    def _is_main_guard(test: ast.expr) -> bool:
        return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == "__name__" and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__")

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            for call in ast.walk(node):
                if isinstance(call, ast.Call):
                    name = _exception_type_name(call)  # reuses the same Call->short-name unwrap
                    if name:
                        out.append(name)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in ("Thread", "create_task")):
            for kw in node.keywords:
                if kw.arg == "target" and isinstance(kw.value, ast.Name):
                    out.append(kw.value.id)
            for arg in node.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                    out.append(arg.func.id)
    return out


# ── BL-14: policy/criticality tagging -- fully automated, no hand-
# maintained field (KNOWLEDGE_SPEC.md Section 3/8 OQ2). Computed once
# RAISES/REGISTERED_ON are known for a symbol, in the same pass -- no need
# for a separate post-merge step since both inputs already exist here. ────
_SECURITY_PATH_KEYWORDS = (
    "auth", "iam", "middleware", "security", "permission", "credential", "secret", "token", "crypto",
)


def _path_keyword_signals(rel_path: str) -> list[str]:
    lower = rel_path.lower()
    return [f"path-keyword:{kw}" for kw in _SECURITY_PATH_KEYWORDS if kw in lower]


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[tuple[str, bool]] = []  # (name, is_class)
        self.symbols: list[dict] = []
        self.calls: list[tuple[str, str | None, str]] = []  # (caller_qualname, receiver, callee_short)
        self.routes: list[tuple[str, str, str]] = []  # (qualname, method, path)
        self.raises: list[tuple[str, str, str | None, int | None]] = []  # (qualname, exc_type, message, status_code)
        self.logs: list[tuple[str, str, str | None]] = []  # (qualname, level, message)
        self.router_prefix = ""

    def _qualname(self, name: str) -> str:
        return ".".join([*(n for n, _ in self.stack), name])

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        qn = self._qualname(node.name)
        self.symbols.append({
            "qualified_name": qn, "kind": "class",
            "docstring_summary": _first_line(ast.get_docstring(node)),
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "is_public": not node.name.startswith("_"),
            "line_start": node.lineno, "line_end": getattr(node, "end_lineno", node.lineno),
            "complexity": None,  # not a meaningful branch-count unit for a class itself
            "bases": [b for b in (_class_ref(x) for x in node.bases) if b],  # ODSF-313, ADR-SDP-DEVKB-006
        })
        self.stack.append((node.name, True))
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qn = self._qualname(node.name)
        kind = "method" if self.stack and self.stack[-1][1] else "function"
        self.symbols.append({
            "qualified_name": qn, "kind": kind,
            "docstring_summary": _first_line(ast.get_docstring(node)),
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "is_public": not node.name.startswith("_"),
            "line_start": node.lineno, "line_end": getattr(node, "end_lineno", node.lineno),
            "complexity": _complexity(node),
        })
        self.calls.extend((qn, receiver, callee) for receiver, callee in _calls_in_body(node))
        self.raises.extend((qn, exc_type, message, status_code)
                            for exc_type, message, status_code in _raises_in_body(node))
        self.logs.extend((qn, level, message) for level, message in _logs_in_body(node))
        for dec in node.decorator_list:
            route = _decorator_route(dec)
            if route:
                method, path = route
                full_path = f"{self.router_prefix}{path}" if self.router_prefix and not path.startswith(self.router_prefix) else path
                self.routes.append((qn, method, full_path))
        self.stack.append((node.name, False))
        self.generic_visit(node)
        self.stack.pop()


def _parse_python_file(
    path: Path,
) -> tuple[list[dict], list[tuple[str, str | None, str]], list[tuple[str, str | None]],
           list[tuple[str, str, str]], str | None, list[tuple[str, str, str | None, int | None]],
           list[tuple[str, str, str | None]], list[tuple[str, str]], str, list[str],
           list[tuple[int, str, str | None, str]], list[str], list[tuple[str, str, str]],
           list[tuple[str, str | None, str, int]]]:
    """Returns (symbols, calls, imports, routes, module_docstring, raises,
    logs, middleware_registrations, router_prefix, daemon_entries,
    import_descriptors, path_literals, typed_calls, value_refs) for one file. An unparseable file yields all-empty,
    not a crash."""
    try:
        text = path.read_text(errors="replace")
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, OSError, ValueError, RecursionError):
        return [], [], [], [], None, [], [], [], "", [], [], [], [], []
    v = _Visitor()
    v.router_prefix = _router_prefix(tree)
    v.visit(tree)
    v.calls.extend((MODULE_CALLER, receiver, callee) for receiver, callee in _module_level_calls(tree))
    module_docstring = ast.get_docstring(tree)
    return (v.symbols, v.calls, _imports(tree), v.routes, module_docstring, v.raises, v.logs,
            _middleware_registrations(tree), v.router_prefix, _daemon_entries(tree), _import_descriptors(tree), _py_literals(tree),
            _typed_calls(tree), _safe_value_refs(tree))


def _safe_value_refs(tree: ast.Module) -> list[tuple[str, str | None, str, int]]:
    try:
        return _value_refs(tree)
    except RecursionError:  # a pathologically deep expression: no references rather than no file
        return []


def extract(repo_root: Path) -> DevKBGraph:
    g = DevKBGraph()

    # ── Pass 1 (Python): parse every file, collect symbols/calls/imports/
    # routes before resolving anything -- cross-file resolution needs every
    # file's own symbol table to already exist. ────────────────────────────
    per_file_symbols: dict[str, list[dict]] = {}
    per_file_calls: dict[str, list[tuple[str, str | None, str]]] = {}
    per_file_imports: dict[str, dict[str, str | None]] = {}
    per_file_literals: dict[str, list[str]] = {}
    per_file_import_targets: dict[str, tuple[dict[str, list[str]], dict[str, tuple[str, str]]]] = {}
    per_file_docstring: dict[str, str | None] = {}
    per_file_raises: dict[str, list[tuple[str, str, str | None, int | None]]] = {}
    per_file_logs: dict[str, list[tuple[str, str, str | None]]] = {}
    per_file_middleware: dict[str, list[tuple[str, str]]] = {}
    per_file_router_prefix: dict[str, str] = {}
    per_file_daemon_entries: dict[str, list[str]] = {}
    per_file_typed_calls: dict[str, list[tuple[str, str, str]]] = {}
    per_file_value_refs: dict[str, list[tuple[str, str | None, str, int]]] = {}
    route_index: dict[str, str] = {}  # "METHOD /path" -> Symbol natural_key
    reexports: dict[str, dict[str, tuple[str, str]]] = {}  # every parsed file's from-imports, symbols or not
    module_callers: dict[str, set[str]] = {}  # called Symbol -> files that call it outside any function

    for rel_path in _list_python_files(repo_root):
        (symbols, calls, imports, routes, module_doc, raises, logs, middleware, router_prefix,
         daemon_entries, descriptors, literals, typed_calls, value_refs) = _parse_python_file(repo_root / rel_path)
        # `@typing.overload` signatures and the implementation share one qualified name, and so one Symbol key: keep
        # one entry (the last, the implementation), or every lookup by name sees several and resolves nothing
        # (click's `prompt`: all 13 call sites were left unattributed).
        symbols = list({s["qualified_name"]: s for s in symbols}.values())
        # Keep the file even with zero functions/classes when it still has
        # something real to attach -- a bare entrypoint (`app.py`: imports
        # + `app.add_middleware(...)` calls, no def/class at all) would
        # otherwise silently lose its own middleware registrations here,
        # a real bug this exact shape caught live (BL-10's own test).
        targets = _import_targets(descriptors, rel_path)
        if targets[1]:
            reexports[rel_path] = targets[1]
        if not symbols and not middleware and not module_doc and not daemon_entries and not calls:
            continue
        per_file_symbols[rel_path] = symbols
        per_file_calls[rel_path] = calls
        per_file_imports[rel_path] = dict(imports)
        per_file_import_targets[rel_path] = targets
        per_file_literals[rel_path] = literals
        per_file_docstring[rel_path] = module_doc
        per_file_raises[rel_path] = raises
        per_file_logs[rel_path] = logs
        per_file_middleware[rel_path] = middleware
        per_file_router_prefix[rel_path] = router_prefix
        per_file_daemon_entries[rel_path] = daemon_entries
        per_file_typed_calls[rel_path] = typed_calls
        per_file_value_refs[rel_path] = value_refs
        for qn, method, path in routes:
            key, owner = f"{method} {path}", f"{rel_path}::{qn}"
            if route_index.get(key, owner) != owner:
                # Two handlers under one "METHOD path" (routers mounted under prefixes this file cannot see): keep
                # both. The first keeps the plain key, which CALLS_API matches; the second is told apart by its file.
                key = f"{method} {path} ({rel_path})"
            route_index[key] = owner

    register_reexports(per_file_symbols, reexports)

    # ── BL-7: persist Endpoint as a real, independently-queryable node --
    # previously route_index only lived as an in-memory resolution
    # intermediate for CALLS_API below, thrown away once built. Natural key
    # matches discovery/'s own "METHOD path" convention exactly, so the two
    # stores stay joinable without a translation table. ─────────────────
    for route_key, owner_symbol in route_index.items():
        method, path = route_key.split(" ", 1)
        path = path.split(" (", 1)[0]  # a disambiguated key carries its file; the path does not
        g.add_node("Endpoint", route_key, source="ast", method=method, path=path, owner_symbol=owner_symbol)

    # security_signals (BL-14) accumulates across RAISES/REGISTERED_ON
    # below, keyed by the owning Symbol's natural_key -- applied to the
    # Symbol node once fully known, at the end of this pass.
    security_signals: dict[str, list[str]] = {}

    for rel_path, symbols in per_file_symbols.items():
        g.add_node("File", rel_path, source="ast", description=per_file_docstring.get(rel_path))
        daemon_entries = set(per_file_daemon_entries.get(rel_path, []))
        for s in symbols:
            natural_key = f"{rel_path}::{s['qualified_name']}"
            is_daemon_entry = s["qualified_name"].rsplit(".", 1)[-1] in daemon_entries
            g.add_node(
                "Symbol", natural_key, source="ast",
                kind=s["kind"], docstring_summary=s["docstring_summary"],
                decorators=s["decorators"], is_public=s["is_public"],
                line_start=s["line_start"], line_end=s["line_end"],
                complexity=s.get("complexity"),
                is_daemon_entry=is_daemon_entry or None,  # add_node strips None -- absent means "no"
            )
            g.add_edge(
                "DEFINED_IN", "Symbol", natural_key, "File", rel_path,
                source="ast", confidence=1.0, evidence_ref=f"{rel_path}:{s['line_start']}",
            )
            for kw in _path_keyword_signals(rel_path):
                security_signals.setdefault(natural_key, []).append(kw)

    # ── BL-9: RAISES + LOGS -> ErrorSignature. Same node type for both
    # sources (a log line and a raised exception with matching text
    # resolve to the same real-world error), status_code only ever set for
    # the HTTPException-literal-int case (RAISES). ─────────────────────
    for rel_path, raises in per_file_raises.items():
        for qn, exc_type, message, status_code in raises:
            caller_key = f"{rel_path}::{qn}"
            sig_key = _error_signature_key("raised", exc_type, message)
            g.add_node("ErrorSignature", sig_key, source="ast", kind="raised", label=exc_type,
                       message_template=message, status_code=status_code)
            confidence = 1.0 if status_code is not None else 0.9
            g.add_edge(
                "RAISES", "Symbol", caller_key, "ErrorSignature", sig_key,
                source="ast", confidence=confidence,
                evidence_ref=f"{rel_path}::{qn} raises {exc_type}",
            )
            if status_code in (401, 403):
                security_signals.setdefault(caller_key, []).append("enforces-authz-boundary")

    for rel_path, logs in per_file_logs.items():
        for qn, level, message in logs:
            caller_key = f"{rel_path}::{qn}"
            sig_key = _error_signature_key("logged", level, message)
            g.add_node("ErrorSignature", sig_key, source="ast", kind="logged", label=level,
                       message_template=message, status_code=None)
            g.add_edge(
                "LOGS", "Symbol", caller_key, "ErrorSignature", sig_key,
                source="ast", confidence=0.85,
                evidence_ref=f"{rel_path}::{qn} logs.{level}(...)",
            )

    # ── BL-10: REGISTERED_ON -- a registration pattern, structurally
    # different from a direct call. Resolves the middleware argument to a
    # real Symbol (same-file, then cross-file via this file's own import,
    # same precedent as CALLS) and targets a wildcard Endpoint (this file's
    # own router_prefix, or the bare app) since middleware wraps every
    # route under it, not one. ──────────────────────────────────────────
    for rel_path, middleware in per_file_middleware.items():
        if not middleware:
            continue
        symbols = per_file_symbols[rel_path]
        local_by_short: dict[str, list[str]] = {}
        bare_by_short: dict[str, list[str]] = {}  # what a bare `name()` can mean: never a method, only `self.name()` is
        method_by_short: dict[str, list[str]] = {}  # what `self.name()` / `cls.name()` can mean in this file
        for s in symbols:
            short = s["qualified_name"].rsplit(".", 1)[-1]
            local_by_short.setdefault(short, []).append(s["qualified_name"])
            (method_by_short if s.get("kind") == "method" else bare_by_short).setdefault(short, []).append(s["qualified_name"])
        imports = per_file_imports.get(rel_path, {})

        for mw_name, receiver in middleware:
            resolved_key = None
            local_targets = local_by_short.get(mw_name, [])
            if len(local_targets) == 1:
                resolved_key = f"{rel_path}::{local_targets[0]}"
            else:
                dotted_module = imports.get(mw_name)
                if dotted_module:
                    resolved_key = _resolve_cross_file_symbol(dotted_module, rel_path, mw_name, per_file_symbols)
            if resolved_key is None:
                continue  # unresolved middleware target -- skip, don't guess

            # Middleware wraps every route under this router/app, not one --
            # a wildcard marker keyed by this file's own router_prefix, with
            # rel_path as a disambiguating fallback for a bare `app` (no
            # prefix) so two different files' own app-level registrations
            # don't collide onto the same wildcard node.
            wildcard_path = per_file_router_prefix.get(rel_path) or rel_path
            endpoint_key = f"* {wildcard_path}"
            g.add_node("Endpoint", endpoint_key, source="ast-middleware-wildcard",
                       method="*", path=wildcard_path, owner_symbol=None)
            g.add_edge(
                "REGISTERED_ON", "Symbol", resolved_key, "Endpoint", endpoint_key,
                source="ast", confidence=0.9,
                evidence_ref=f"{rel_path}: {receiver}.add_middleware({mw_name})",
            )
            security_signals.setdefault(resolved_key, []).append("registered-as-middleware")

    for natural_key, signals in security_signals.items():
        g.add_node("Symbol", natural_key, source="ast", security_signals=sorted(set(signals)))

    # ── ODSF-313: class bases, used to resolve a method call through inheritance into an ordinary CALLS edge. The
    # CONTAINS/EXTENDS edges ADR-SDP-DEVKB-006 proposes are NOT emitted while it is Proposed: no new verb without an
    # Accepted ADR (ADR-SDP-DEVKB-001). Calls resolved through a base carry source ast-typed-receiver-base, so the
    # audit (ODSF-314) can count exactly what inheritance adds. ─────────────────────────────────────────────
    class_bases: dict[str, list[str]] = {}
    for rel_path, symbols in per_file_symbols.items():
        targets = per_file_import_targets.get(rel_path, ({}, {}))
        for s in symbols:
            qn = s["qualified_name"]
            if s["kind"] == "class":
                for base in s.get("bases") or []:
                    base_key = _resolve_class(base, rel_path, per_file_symbols, targets)
                    if base_key and base_key != f"{rel_path}::{qn}":
                        class_bases.setdefault(f"{rel_path}::{qn}", []).append(base_key)

    # Every call site the resolver leaves unattributed, by the called name, when some symbol in the repository has
    # that name: the coverage a list answer must report instead of looking complete (ODSF-313).
    repo_short_names = {s["qualified_name"].rsplit(".", 1)[-1] for symbols in per_file_symbols.values() for s in symbols}
    unresolved: set[tuple[str, str, str]] = set()  # (file, caller qualname, called name)

    # ── Pass 2 (Python, BL-3b): resolve calls -- same-file first (0.8,
    # unchanged from BL-3), then cross-file via THIS file's own import of
    # the receiver/callee (0.7 -- one hop of real, evidence-backed
    # indirection, still not a guess). No project-wide "unique short name
    # anywhere" fallback -- too easy for a common name (get, run, main) to
    # silently resolve to the wrong file; missing a match beats
    # mis-attributing one. ──────────────────────────────────────────────
    for rel_path, calls in per_file_calls.items():
        symbols = per_file_symbols[rel_path]
        local_by_short: dict[str, list[str]] = {}
        bare_by_short: dict[str, list[str]] = {}  # what a bare `name()` can mean: never a method, only `self.name()` is
        method_by_short: dict[str, list[str]] = {}  # what `self.name()` / `cls.name()` can mean in this file
        for s in symbols:
            short = s["qualified_name"].rsplit(".", 1)[-1]
            local_by_short.setdefault(short, []).append(s["qualified_name"])
            (method_by_short if s.get("kind") == "method" else bare_by_short).setdefault(short, []).append(s["qualified_name"])
        imports = per_file_imports.get(rel_path, {})

        receivers_here = per_file_import_targets.get(rel_path, ({}, {}))[0]
        receivers_dotted = per_file_import_targets.get(rel_path, ({}, {}))[0]
        for caller_qn, receiver, callee_short in calls:
            caller_key = f"{rel_path}::{caller_qn}"
            dotted_hit = None
            if receiver and "." in receiver and receiver != EXPR:
                root, rest = receiver.split(".", 1)
                for module in receivers_dotted.get(root, []):
                    dotted_hit = _resolve_cross_file_symbol(f"{module}.{rest}", rel_path, callee_short, per_file_symbols)
                    if dotted_hit:
                        break
                if dotted_hit is None:
                    receiver = EXPR  # a chain not through an imported module: an expression, as before
            if dotted_hit:
                if caller_qn == MODULE_CALLER:
                    module_callers.setdefault(dotted_hit, set()).add(rel_path)
                else:
                    g.add_edge("CALLS", "Symbol", caller_key, "Symbol", dotted_hit, source="ast-cross-file-import",
                               confidence=0.7, evidence_ref=f"{rel_path}::{caller_qn} calls {receiver}.{callee_short}")
                continue

            # `mod.f()` on an imported name calls the import's `f`, never a same-named function of this file: a
            # handler `create_x` calling `models.create_x(...)` was recorded as calling itself, and the real chain
            # into the models layer was lost.
            # Same file: a bare `f()` is a function or class of this file; `self.f()` / `cls.f()` a method of it. A call on
            # any other object (`path.resolve()`, an imported module) is never a same-file function: the typed-receiver
            # and import passes decide those, and `as_path.resolve()` inside `def resolve` was recorded as recursion.
            local_targets = (method_by_short.get(callee_short, []) if receiver in ("self", "cls") else []) if receiver \
                else bare_by_short.get(callee_short, [])
            if len(local_targets) == 1 and caller_qn == MODULE_CALLER:
                module_callers.setdefault(f"{rel_path}::{local_targets[0]}", set()).add(rel_path)
                continue
            if len(local_targets) == 1:
                g.add_edge(
                    "CALLS", "Symbol", caller_key, "Symbol", f"{rel_path}::{local_targets[0]}",
                    source="ast-same-file", confidence=0.8,
                    evidence_ref=f"{rel_path}::{caller_qn} calls {callee_short}",
                )
                continue

            receivers, bare = per_file_import_targets.get(rel_path, ({}, {}))
            resolved_key = None
            # ODSF-305: resolve through what the file actually imported --
            # a module alias, `from pkg import module`, a relative import.
            if receiver:
                for module in receivers.get(receiver, []):
                    resolved_key = _resolve_cross_file_symbol(module, rel_path, callee_short, per_file_symbols)
                    if resolved_key:
                        break
            elif callee_short in bare:
                module, original = bare[callee_short]
                resolved_key = _resolve_cross_file_symbol(module, rel_path, original, per_file_symbols)
            if resolved_key is None and receiver and receiver not in receivers and receiver.isidentifier():
                # A module loaded with importlib and bound to a variable of the same name.
                resolved_key = _resolve_cross_file_symbol(receiver, rel_path, callee_short, per_file_symbols)
            if receiver == EXPR:
                if callee_short in repo_short_names:
                    unresolved.add((rel_path, caller_qn, callee_short))  # said in coverage, as before: not attributed
                continue
            if resolved_key is None and receiver and receiver not in receivers:
                resolved_key = _resolve_via_literals(per_file_literals.get(rel_path, []), callee_short, per_file_symbols)
            if resolved_key is None:
                dotted_module = imports.get(receiver) if receiver else imports.get(callee_short)
                if dotted_module is None and receiver is None and callee_short not in imports:
                    if callee_short in repo_short_names and len(local_targets) != 1:
                        unresolved.add((rel_path, caller_qn, callee_short))
                    continue  # nothing to resolve against
                if dotted_module:
                    resolved_key = _resolve_cross_file_symbol(dotted_module, rel_path, callee_short, per_file_symbols)
            if resolved_key and caller_qn == MODULE_CALLER:
                module_callers.setdefault(resolved_key, set()).add(rel_path)
            elif resolved_key:
                g.add_edge(
                    "CALLS", "Symbol", caller_key, "Symbol", resolved_key,
                    source="ast-cross-file-import", confidence=0.7,
                    evidence_ref=f"{rel_path}::{caller_qn} calls {receiver + '.' if receiver else ''}{callee_short}",
                )
            elif callee_short in repo_short_names:
                unresolved.add((rel_path, caller_qn, callee_short))

    # ── ODSF-312: calls on an instance of a class the code names ────────────
    for rel_path, typed in per_file_typed_calls.items():
        targets = per_file_import_targets.get(rel_path, ({}, {}))
        for caller_qn, cls_ref, method in typed:
            resolved_key = _resolve_typed_call(cls_ref, method, rel_path, per_file_symbols, targets, class_bases)
            via_base = bool(resolved_key and resolved_key.endswith("#base"))
            resolved_key = resolved_key[: -len("#base")] if via_base else resolved_key
            if resolved_key and resolved_key != f"{rel_path}::{caller_qn}":
                g.add_edge(
                    "CALLS", "Symbol", f"{rel_path}::{caller_qn}", "Symbol", resolved_key,
                    source="ast-typed-receiver-base" if via_base else "ast-typed-receiver", confidence=0.6,
                    evidence_ref=f"{rel_path}::{caller_qn} calls {method} on a {cls_ref.replace('self:', '')}",
                )
                unresolved.discard((rel_path, caller_qn, method))

    by_name: dict[str, dict[str, int]] = {}
    for rel_path, _caller, name in unresolved:
        by_name.setdefault(name, {})[rel_path] = by_name.setdefault(name, {}).get(rel_path, 0) + 1
    for rel_path, symbols in per_file_symbols.items():
        for s in symbols:
            files = by_name.get(s["qualified_name"].rsplit(".", 1)[-1])
            if files:
                ranked = sorted(files, key=lambda f: (-files[f], f))
                g.add_node("Symbol", f"{rel_path}::{s['qualified_name']}", source="ast",
                           unresolved_calls=sum(files.values()), unresolved_files=ranked[:20],
                           unresolved_file_count=len(ranked))
    for key, files in module_callers.items():
        g.add_node("Symbol", key, source="ast", module_callers=sorted(files))

    # ── #69: a function or method named without being called (`pool.submit(self._moved_files, rev)`, `key=key_of`, a
    # dispatch table) is called where the graph cannot see. Not a CALLS edge, which would claim a call: the sites are
    # kept on the Symbol, and its coverage is Incomplete with the existing `indirect-reference` reason. Resolved the
    # way a call is: `self.f`/`cls.f` to the one method of that name in the file, a bare name to the one function of
    # the file, else through this file's own `from m import f`. ─────────────────────────────────────────────────────
    kind_of = {f"{rel}::{s['qualified_name']}": s.get("kind") for rel, syms in per_file_symbols.items() for s in syms}
    value_refs: dict[str, set[str]] = {}
    for rel_path, refs in per_file_value_refs.items():
        bare_here: dict[str, list[str]] = {}
        method_here: dict[str, list[str]] = {}
        for s in per_file_symbols.get(rel_path, []):
            if s.get("kind") in ("function", "method"):
                (method_here if s["kind"] == "method" else bare_here).setdefault(
                    s["qualified_name"].rsplit(".", 1)[-1], []).append(s["qualified_name"])
        bare_imports = per_file_import_targets.get(rel_path, ({}, {}))[1]
        for scope, receiver, name, line in refs:
            local = method_here.get(name, []) if receiver else bare_here.get(name, [])
            target = f"{rel_path}::{local[0]}" if len(local) == 1 else None
            if target is None and receiver is None and not local and name in bare_imports:
                module, original = bare_imports[name]
                hit = _resolve_cross_file_symbol(module, rel_path, original, per_file_symbols)
                target = hit if hit and kind_of.get(hit) in ("function", "method") else None
            if target and target != f"{rel_path}::{scope}":
                value_refs.setdefault(target, set()).add(f"{rel_path}:{line}")
    for key, sites in value_refs.items():
        ranked = sorted(sites, key=lambda x: (x.rsplit(":", 1)[0], int(x.rsplit(":", 1)[1])))
        g.add_node("Symbol", key, source="ast", value_refs=ranked[:20], value_ref_count=len(ranked),
                   incomplete_reasons=["indirect-reference"])

    # ── BL-3c: TypeScript/TSX Symbols + their own route-call sites ─────────
    ts_route_calls: list[tuple[str, str, str, str]] = []  # (file, symbol_qn, method, path)
    ts_files = _list_ts_files(repo_root)
    helpers = ts_symbols.collect_url_helpers([repo_root / rel for rel in ts_files])  # ODSF-314: builders, wrappers
    for rel_path in ts_files:
        symbols, route_calls = ts_symbols.extract_file(repo_root / rel_path, repo_root, helpers)
        if not symbols:
            continue
        g.add_node("File", rel_path, source="ast-ts")
        for s in symbols:
            natural_key = f"{rel_path}::{s['qualified_name']}"
            g.add_node(
                "Symbol", natural_key, source="ast-ts",
                kind=s["kind"], docstring_summary=None, decorators=[], is_public=True,
                line_start=s["line_start"], line_end=s["line_start"],
            )
            g.add_edge(
                "DEFINED_IN", "Symbol", natural_key, "File", rel_path,
                source="ast-ts", confidence=1.0, evidence_ref=f"{rel_path}:{s['line_start']}",
            )
        for symbol_qn, method, path in route_calls:
            ts_route_calls.append((rel_path, symbol_qn, method, path))

    # ── C#: type and member definitions, and the calls between them (SPEC-DEVKB-CSHARP) ──
    csharp_symbols.add_to_graph(g, repo_root)

    # ── ODSF-304: Odoo XML declarations (templates, views, actions, menus) ──
    for rel_path, decls in _odoo_xml_symbols(repo_root).items():
        g.add_node("File", rel_path, source="odoo-xml")
        for d in decls:
            natural_key = f"{rel_path}::{d['qualified_name']}"
            g.add_node(
                "Symbol", natural_key, source="odoo-xml",
                kind=d["kind"], docstring_summary=None, decorators=[], is_public=True,
                line_start=d["line_start"], line_end=d["line_start"],
            )
            g.add_edge(
                "DEFINED_IN", "Symbol", natural_key, "File", rel_path,
                source="odoo-xml", confidence=1.0, evidence_ref=f"{rel_path}:{d['line_start']}",
            )

    # ── BL-4b: resolve each frontend route-call against the real backend
    # Symbol that handles it -- CALLS_API, the actual UI-action-to-code
    # connective tissue. Unresolved (no matching backend route found, e.g.
    # the path has a runtime prefix this scan can't see) is left
    # unresolved, not guessed. ──────────────────────────────────────────
    # ODSF-314: compare route shapes, so `/jobs/{job_id}` matches a call built as `/jobs/${id}`; a call whose method
    # the extractor could not read matches a path with exactly one route.
    by_shape: dict[tuple[str, str], str] = {}
    by_path: dict[str, list[str]] = {}
    for route_key, owner in route_index.items():
        m, p = route_key.split(" ", 1)
        shape = ts_symbols.route_shape(p.split(" (", 1)[0])
        # a path two handlers serve is ambiguous: a call to it stays unresolved rather than picking one
        by_shape[(m, shape)] = owner if by_shape.get((m, shape), owner) == owner else None
        by_path.setdefault(shape, []).append(owner)
    for file_path, symbol_qn, method, path in ts_route_calls:
        target = route_index.get(f"{method} {path}") or by_shape.get((method, ts_symbols.route_shape(path)))
        if target is None and len(set(by_path.get(ts_symbols.route_shape(path), []))) == 1:
            target = by_path[ts_symbols.route_shape(path)][0]
        if target is None:
            continue
        g.add_edge(
            "CALLS_API", "Symbol", f"{file_path}::{symbol_qn}", "Symbol", target,
            source="ast-route-match", confidence=0.85,
            evidence_ref=f"{file_path}::{symbol_qn} calls {method} {path}",
        )

    # ── ADR-DEVKB-008: C and C++ (one call; every C/C++ rule lives in cpp_graph) ──
    cpp_graph.add_to_graph(g, repo_root, _error_signature_key)

    return g


def load_cache(ctx: ProjectContext) -> DevKBGraph:
    """Reconstructs a DevKBGraph from `.devkb/symbols-{nodes,edges}.jsonl`
    -- the regular devkb/build.py calls this to merge BL-3's already-built
    Symbol graph into the main store, never regenerating it itself. Missing
    cache (no refresh run yet) returns an empty graph, not an error -- same
    "can't check yet" framing used elsewhere in devkb.

    Node dicts keep their own natural_key, so those round-trip directly.
    Edge dicts only persist from_uid/to_uid (the hashed form, per
    Edge.to_dict()), so reconstructing a real add_edge() call needs a
    uid -> (type, natural_key) reverse lookup built from the nodes pass
    first -- an edge referencing a uid missing from that map (a corrupt or
    hand-edited cache) is skipped, not a crash."""
    g = DevKBGraph()
    nodes_path = ctx.devkb_dir / "symbols-nodes.jsonl"
    edges_path = ctx.devkb_dir / "symbols-edges.jsonl"
    if not nodes_path.exists():
        return g

    uid_to_key: dict[str, tuple[str, str]] = {}
    for line in nodes_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        n = json.loads(line)
        g.add_node(n["type"], n["natural_key"], source=n.get("source", "cache"), **n.get("properties", {}))
        uid_to_key[n["uid"]] = (n["type"], n["natural_key"])

    if edges_path.exists():
        for line in edges_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            src = uid_to_key.get(e["from_uid"])
            dst = uid_to_key.get(e["to_uid"])
            if src is None or dst is None:
                continue
            props = e.get("properties", {})
            extra = {k: v for k, v in props.items() if k not in ("source", "confidence", "evidence_ref")}
            g.add_edge(
                e["verb"], src[0], src[1], dst[0], dst[1],
                source=props.get("source", "cache"), confidence=props.get("confidence", 1.0),
                evidence_ref=props.get("evidence_ref", ""), extra=extra,
            )
    return g


def build(code: str) -> tuple[DevKBGraph, Path]:
    ctx = resolve(code)
    graph = extract(ctx.repo_root)

    ctx.devkb_dir.mkdir(parents=True, exist_ok=True)
    data = graph.to_dict()

    nodes_path = ctx.devkb_dir / "symbols-nodes.jsonl"
    edges_path = ctx.devkb_dir / "symbols-edges.jsonl"
    manifest_path = ctx.devkb_dir / "symbols-manifest.json"

    nodes_path.write_text("\n".join(json.dumps(n) for n in data["nodes"]) + ("\n" if data["nodes"] else ""))
    edges_path.write_text("\n".join(json.dumps(e) for e in data["edges"]) + ("\n" if data["edges"] else ""))
    manifest_path.write_text(json.dumps({
        "project": code,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(ctx.repo_root),
        "node_count": graph.node_count(),
        "edge_count": graph.edge_count(),
        **({"cpp": graph.meta["cpp"]} if graph.meta.get("cpp") else {}),
    }, indent=2))

    return graph, ctx.devkb_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh devkb's Symbol graph for one project (BL-3, standalone)")
    ap.add_argument("--project", required=True, help="Project code, e.g. ODSF (see projects.json)")
    # `devkb build` hands the same arguments to this and to build.py; the GitHub layer belongs to the latter.
    ap.add_argument("--github", action="store_true", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--no-github", dest="github", action="store_false", help=argparse.SUPPRESS)
    args = ap.parse_args()

    try:
        graph, devkb_dir = build(args.project)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"devkb symbol refresh ({args.project}): {graph.node_count()} nodes, {graph.edge_count()} edges "
          f"-> {devkb_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
