"""Python side of the cross-language records (ADR-DEVKB-009 §3): a call into a C library or an extension module.

`extract(repo_root, files)` returns import records (`boundaries.Record`) and never touches the graph. A call
`lib.name(...)` is a boundary only when `lib` is provably a library handle: bound by `ctypes.CDLL(...)`, `PyDLL`,
`WinDLL`, `cdll.LoadLibrary(...)` (mechanism `ctypes`) or `<ffi>.dlopen(...)` (`cffi`). `getattr(lib, name)(...)` with a
name that is not a literal is a dynamic import. A call `mod.name(...)` on an imported module (or `name(...)` from
`from mod import name`) is an extension-module import (`pyc-api`); the resolver drops it unless some C or C++ file
exports `mod.name`. Symbol keys follow `build_symbols`: `<path>::<Class.func>`.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from devkb.boundaries import Record

_CTYPES_LOADERS = {"CDLL", "PyDLL", "WinDLL", "OleDLL"}
MAX_PY_BYTES = 1024 * 1024


def list_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.py"], cwd=repo_root, capture_output=True,
                          text=True, check=False)
    return sorted({f for f in proc.stdout.splitlines() if f.strip()})


def _handle_kind(call: ast.AST) -> str | None:
    """`ctypes` or `cffi` when this expression creates a library handle."""
    if not isinstance(call, ast.Call):
        return None
    f = call.func
    if isinstance(f, ast.Attribute):
        if f.attr in _CTYPES_LOADERS:
            return "ctypes"
        if f.attr == "LoadLibrary" and isinstance(f.value, (ast.Name, ast.Attribute)) and ast.unparse(f.value).split(".")[-1] == "cdll":
            return "ctypes"
        if f.attr == "dlopen":
            return "cffi"
    elif isinstance(f, ast.Name) and f.id in _CTYPES_LOADERS:
        return "ctypes"
    return None


class _Walker(ast.NodeVisitor):
    def __init__(self, rel: str, out: list[Record]) -> None:
        self.rel, self.out = rel, out
        self.stack: list[str] = []
        self.handles: list[dict[str, str]] = [{}]          # scope chain: name -> mechanism
        self.modules: dict[str, str] = {}                 # local name -> imported top-level module
        self.members: dict[str, tuple[str, str]] = {}     # local name -> (module, member)

    # imports ---------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for a in node.names:
            if "." not in a.name:
                self.modules[a.asname or a.name] = a.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module and "." not in node.module and not node.level:
            for a in node.names:
                if a.name != "*":
                    self.members[a.asname or a.name] = (node.module, a.name)

    # scopes ----------------------------------------------------------------
    def _scope(self, node, name: str) -> None:
        self.stack.append(name)
        self.handles.append({})
        self.generic_visit(node)
        self.handles.pop()
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        kind = _handle_kind(node.value)
        if kind:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.handles[-1][t.id] = kind
        self.generic_visit(node)

    # calls -----------------------------------------------------------------
    def _handle(self, name: str) -> str | None:
        for scope in reversed(self.handles):
            if name in scope:
                return scope[name]
        return None

    def _caller(self) -> str | None:
        return f"{self.rel}::{'.'.join(self.stack)}" if len(self.handles) > 1 and self.stack else None

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        caller = self._caller()
        f = node.func
        if caller:
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                kind = self._handle(f.value.id)
                if kind:
                    self.out.append(Record("import", f.attr, kind, self.rel, node.lineno, caller, language="python"))
                elif f.value.id in self.modules:
                    self.out.append(Record("import", f"{self.modules[f.value.id]}.{f.attr}", "pyc-api", self.rel, node.lineno, caller,
                                           language="python"))
            elif isinstance(f, ast.Name) and f.id in self.members and not self._handle(f.id):
                mod, member = self.members[f.id]
                self.out.append(Record("import", f"{mod}.{member}", "pyc-api", self.rel, node.lineno, caller, language="python"))
            elif isinstance(f, ast.Call) and isinstance(f.func, ast.Name) and f.func.id == "getattr" and len(f.args) >= 2 \
                    and isinstance(f.args[0], ast.Name):
                kind = self._handle(f.args[0].id)
                if kind:
                    name = f.args[1]
                    if isinstance(name, ast.Constant) and isinstance(name.value, str):
                        self.out.append(Record("import", name.value, kind, self.rel, node.lineno, caller, language="python"))
                    else:
                        self.out.append(Record("import", "", kind, self.rel, node.lineno, caller, dynamic=True, language="python"))
        self.generic_visit(node)


def extract(repo_root: Path, files: list[str] | None = None) -> list[Record]:
    out: list[Record] = []
    for rel in files if files is not None else list_files(repo_root):
        try:
            p = repo_root / rel
            if p.stat().st_size > MAX_PY_BYTES:
                continue
            text = p.read_text(errors="replace")
            if "import" not in text:
                continue
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        _Walker(rel, out).visit(tree)
    return out
