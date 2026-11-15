"""Import-path call truth for the confirmatory study (ODSF-315, PREREGISTRATION.md deviation D1).

The exploratory truth (workflow_tasks.callers_of) matches a call by the called NAME and keeps only names defined once
in the repository. Public FastAPI projects define `get`, `create` and `update` in dozens of `service.py` modules, so
on Netflix Dispatch that rule left one usable task. This truth resolves a call through the caller file's imports to
the MODULE that defines the function, so equal names in different modules never meet:

  from dispatch.incident import service    ->  service.get(...)   ->  dispatch/incident/service.py::get
  from dispatch.incident.service import get -> get(...)           ->  dispatch/incident/service.py::get
  import dispatch.incident.service as svc  ->  svc.get(...)        ->  dispatch/incident/service.py::get
  a call to a function defined in the same file, by its bare name

Targets are module-level functions, and methods called as `self.x()` / `cls.x()` from their own class in the same
file. A call made through any other object (`store.x()`), or reaching a method through a base class, is not
attributed: the truth is conservative, so a task is built only on functions whose callers it can see completely (no
method on the path except a route handler, whose own callers in its class are followed).

A name imported from a package that re-exports it (`from lnbits.core.crud import get_wallet`, with
`from .wallets import get_wallet` in `crud/__init__.py`) is followed to the module that defines it. A call made outside
every function (`app_dirs = get_app_dirs()` at import time, or in a class body) has the caller `<module>`: it counts
for the files a signature change breaks, and is not a function on a call chain.

A raised message is the first positional string argument, or a `detail=` / `message=` / `msg=` / `description=`
keyword (`HTTPException(status_code=422, detail="...")`).
"""
from __future__ import annotations

import ast
import collections
import re
import subprocess
from pathlib import Path

ROUTE_VERBS = {"get", "post", "put", "delete", "patch"}
RAISE_KEYWORDS = ("detail", "message", "msg", "description")
MODULE = "<module>"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")


def is_test(path: str) -> bool:
    return bool(_TEST.search(path))


class _File(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.stack: list[str] = []
        self.fn: list[str] = []
        self.functions: set[str] = set()         # module-level function names
        self.defs: dict[str, tuple[int, bool]] = {}  # qualname -> (line, is_route)
        self.calls: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)  # caller qual -> {(base, name)}
        self.bind_mod: dict[str, str] = {}       # local -> dotted module
        self.bind_obj: dict[str, tuple[str, str]] = {}  # local -> (dotted module, name)
        self.raises: list[tuple[str, str]] = []
        self.classes: list[str] = []             # qualnames of the enclosing classes, innermost last

    def visit_Import(self, node):
        for a in node.names:
            if a.asname:
                self.bind_mod[a.asname] = a.name
            else:
                self.bind_mod[a.name.split(".")[0]] = a.name.split(".")[0]

    def visit_ImportFrom(self, node):
        if node.level:
            parts = self.rel[:-3].split("/")[:-1]
            base = parts[: len(parts) - (node.level - 1)] if node.level - 1 <= len(parts) else []
            mod = ".".join(base + ([node.module] if node.module else []))
        else:
            mod = node.module or ""
        for a in node.names:
            if a.name != "*":
                self.bind_obj[a.asname or a.name] = (mod, a.name)

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.classes.append(".".join(self.stack))
        self.generic_visit(node)
        self.classes.pop()
        self.stack.pop()

    def _fn(self, node):
        qual = ".".join(self.stack + [node.name])
        if not self.stack:
            self.functions.add(node.name)
        is_route = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS
                       for d in node.decorator_list)
        self.defs[qual] = (node.lineno, is_route)
        self.stack.append(node.name)
        self.fn.append(qual)
        self.generic_visit(node)
        self.fn.pop()
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_Call(self, node):
        caller = self.fn[-1] if self.fn else MODULE
        f = node.func
        if isinstance(f, ast.Name):
            self.calls[caller].add(("", f.id))
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if f.value.id in ("self", "cls") and self.classes:
                if self.fn:
                    self.calls[caller].add((f"self:{self.classes[-1]}", f.attr))  # the innermost enclosing class
            else:
                self.calls[caller].add((f.value.id, f.attr))
        elif isinstance(f, ast.Attribute):  # `prefect.context.get_run_context()` after `import prefect.context`
            parts, v = [], f.value
            while isinstance(v, ast.Attribute):
                parts.insert(0, v.attr)
                v = v.value
            if isinstance(v, ast.Name) and v.id not in ("self", "cls"):
                self.calls[caller].add((".".join([v.id, *parts]), f.attr))
        self.generic_visit(node)

    def visit_Lambda(self, node):  # a lambda's body runs when it is called, not at import: no module-level call
        if self.fn:
            self.generic_visit(node)

    def visit_Raise(self, node):
        if self.fn and isinstance(node.exc, ast.Call):
            cands = node.exc.args[:1] + [k.value for k in node.exc.keywords if k.arg in RAISE_KEYWORDS]
            a = next((c for c in cands if isinstance(c, ast.Constant) and isinstance(c.value, str)), None)
            if a is not None:
                self.raises.append((self.fn[-1], a.value))
        self.generic_visit(node)


class Truth:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: dict[str, _File] = {}
        listed = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.py"], cwd=root,
                                capture_output=True, text=True).stdout.split()
        for rel in listed:
            # migrations and alembic versions are callers too: a signature change breaks them like any other file
            if re.search(r"(^|/)(\.impl-worktrees|node_modules|\.claude|_bmad)/", rel):
                continue
            try:
                v = _File(rel)
                v.visit(ast.parse((root / rel).read_text(errors="replace")))
            except (SyntaxError, ValueError, OSError, RecursionError):
                continue
            self.files[rel] = v
        self.suffix: dict[str, list[str]] = collections.defaultdict(list)
        for rel in self.files:
            mod = rel[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            parts = mod.split(".")
            for i in range(len(parts)):
                self.suffix[".".join(parts[i:])].append(rel)
        self._callers: dict[tuple[str, str], set[tuple[str, str]]] | None = None

    def module_file(self, dotted: str) -> str | None:
        """The one file a dotted module names, by its longest unique path suffix."""
        hits = self.suffix.get(dotted, [])
        return hits[0] if len(hits) == 1 else None

    def _defined(self, target: str | None, name: str, depth: int = 0) -> tuple[str, str] | None:
        """(file, name) where `name`, looked up in module file `target`, is defined: there, or through the import that
        makes it importable from there (a package's `__init__.py` re-export), a bounded number of hops."""
        if target is None:
            return None
        if name in self.files[target].functions:
            return (target, name)
        via = self.files[target].bind_obj.get(name)
        if via and depth < 6:
            return self._defined(self.module_file(via[0]), via[1], depth + 1)
        return None

    def _target(self, rel: str, base: str, name: str) -> tuple[str, str] | None:
        f = self.files[rel]
        if base.startswith("self:"):
            qual = f"{base[5:]}.{name}"
            return (rel, qual) if qual in f.defs else None
        if not base:
            if name in f.bind_obj:
                mod, orig = f.bind_obj[name]
                return self._defined(self.module_file(mod), orig)
            return (rel, name) if name in f.functions else None
        if "." in base:  # a module path: its root must be an imported module
            root, rest = base.split(".", 1)
            if root in f.bind_mod:
                return self._defined(self.module_file(f"{f.bind_mod[root]}.{rest}"), name)
            if root in f.bind_obj:
                mod, orig = f.bind_obj[root]
                return self._defined(self.module_file(".".join(x for x in (mod, orig, rest) if x)), name)
            return None
        dotted = f.bind_mod.get(base)
        if dotted is None and base in f.bind_obj:
            mod, orig = f.bind_obj[base]
            dotted = f"{mod}.{orig}" if mod else orig
        if dotted is None:
            return None
        return self._defined(self.module_file(dotted), name)

    def callers(self) -> dict[tuple[str, str], set[tuple[str, str]]]:
        if self._callers is None:
            out: dict[tuple[str, str], set[tuple[str, str]]] = collections.defaultdict(set)
            for rel, f in self.files.items():
                for caller, calls in f.calls.items():
                    for base, name in calls:
                        t = self._target(rel, base, name)
                        if t and t != (rel, caller):
                            out[t].add((rel, caller))
            self._callers = out
        return self._callers

    def is_route(self, key: tuple[str, str]) -> bool:
        return self.files[key[0]].defs.get(key[1], (0, False))[1]

    def is_function(self, key: tuple[str, str]) -> bool:
        return "." not in key[1] and key[1] in self.files[key[0]].functions

    def up(self, start: tuple[str, str], max_depth: int = 6) -> tuple[set, set, bool]:
        """(production callers, test callers, clean). Clean when every production caller on the way is a module-level
        function whose own callers the truth sees, or a route handler, where a path ends."""
        callers = self.callers()
        prod, tests, clean = set(), set(), True
        frontier = [start]
        for _ in range(max_depth):
            nxt = []
            for k in frontier:
                for c in callers.get(k, ()):
                    if c in prod or c in tests or c[1] == MODULE:
                        continue  # an import-time call is no function on a chain
                    if is_test(c[0]):
                        tests.add(c)
                        continue
                    prod.add(c)
                    if self.is_route(c):
                        nxt.append(c)  # a handler may itself be called by another handler of its class
                        continue
                    if not self.is_function(c):
                        clean = False
                        continue
                    nxt.append(c)
            frontier = nxt
            if not frontier:
                break
        else:
            clean = clean and not frontier
        return prod, tests, clean


def short(key: tuple[str, str]) -> str:
    return f"{key[0]}::{key[1].split('.')[-1]}"
