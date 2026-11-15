"""Content-based test linkage (devkb BL-4, body/legs model).

Phase 2's TESTED_BY needs a ticket ID literally mentioned near the test --
doubly ticket-dependent (a ticket to find the commit, a ticket mention in
the test). This resolves real evidence instead: a test function's own
imports matched against Symbol natural keys (BL-3), scoped to calls that
function's own body actually makes -- not "the file imports it somewhere,"
which would just move Phase 2's coarseness from ticket-level to file-level
instead of removing it. Additive alongside Phase 2's existing
0.7-confidence ticket-mediated edges, never a replacement.

Needs BL-3's Symbol nodes already in `graph` (build.py merges the symbols
cache before calling this) -- an empty/missing Symbol set just means zero
edges here, not an error, same "can't check yet" framing used elsewhere in
devkb for a missing input.
"""
from __future__ import annotations

import ast

from devkb.build_symbols import (
    EXPR, _calls_in_body, _import_descriptors, _import_targets, _imports, _module_paths, _py_literals,
    _list_python_files, _resolve_cross_file_symbol, _resolve_via_literals, collect_reexports, register_reexports,
)
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext
from devkb.test_discovery import list_test_files


def _test_functions(tree: ast.AST) -> list[tuple[str, int, set[str], set[tuple[str | None, str]]]]:
    """[(name, lineno, {short names this function's own body calls}), ...]
    -- reuses BL-3's own body-scoped call scanner (build_symbols.py) so a
    nested helper's calls don't get misattributed to the outer test. Only
    the short callee name is used here (not _calls_in_body's receiver,
    which BL-3b's own cross-file CALLS resolution needs but this doesn't --
    a test's own import-name match is already the precise signal)."""
    out: list[tuple[str, int, set[str], set[tuple[str | None, str]]]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            pairs = set(_calls_in_body(node))
            out.append((node.name, node.lineno, {short for _receiver, short in pairs}, pairs))
    return out


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    g = DevKBGraph()
    by_short_name: dict[str, list[str]] = {}
    for s in graph.nodes("Symbol"):
        short = s.natural_key.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
        by_short_name.setdefault(short, []).append(s.natural_key)
    if not by_short_name:
        return g
    # path -> [{"qualified_name": ...}], the shape _resolve_cross_file_symbol reads (ODSF-305).
    symbols_by_file: dict[str, list[dict]] = {}
    for s in graph.nodes("Symbol"):
        path, _, qualified = s.natural_key.partition("::")
        symbols_by_file.setdefault(path, []).append({"qualified_name": qualified})
    # `from pkg import f` where `pkg/__init__.py` re-exports f from a submodule
    register_reexports(symbols_by_file, collect_reexports(ctx.repo_root, _list_python_files(ctx.repo_root)))

    # ODSF-304: every tracked python test file, wherever it lives.
    for py in (ctx.repo_root / rel for rel in list_test_files(ctx.repo_root, ctx.tests_dir) if rel.endswith(".py")):
        try:
            text = py.read_text(errors="replace")
            tree = ast.parse(text, filename=str(py))
        except (SyntaxError, OSError, ValueError):
            continue
        rel = str(py.relative_to(ctx.repo_root))
        imported = _imports(tree)
        tests = _test_functions(tree)
        if not tests:
            continue

        receivers, bare = _import_targets(_import_descriptors(tree), rel)
        literals = _py_literals(tree)
        for name, lineno, calls, pairs in tests:
            resolved: set[str] = set()
            # ODSF-305: `module.func()` and aliased or relative imports.
            for receiver, short in pairs:
                if receiver and "." in receiver and receiver != EXPR:  # `pkg.mod.f()` after `import pkg.mod`
                    root, rest = receiver.split(".", 1)
                    modules = [f"{m}.{rest}" for m in receivers.get(root, [])]
                    hit = next((h for h in (_resolve_cross_file_symbol(m, rel, short, symbols_by_file) for m in modules) if h), None)
                    if hit:
                        resolved.add(hit)
                    continue
                if receiver:
                    modules = receivers.get(receiver) or ([receiver] if receiver.isidentifier() else [])
                    hit = None
                    for module in modules:
                        hit = _resolve_cross_file_symbol(module, rel, short, symbols_by_file)
                        if hit:
                            break
                    if hit is None and receiver not in receivers:
                        hit = _resolve_via_literals(literals, short, symbols_by_file)
                    if hit:
                        resolved.add(hit)
                elif short in bare:
                    module, original = bare[short]
                    hit = _resolve_cross_file_symbol(module, rel, original, symbols_by_file)
                    if hit:
                        resolved.add(hit)
            for local_name, dotted_module in imported:
                if local_name not in calls:
                    continue
                candidates = by_short_name.get(local_name, [])
                if not candidates:
                    continue
                target = None
                if dotted_module:
                    for guess in _module_paths(dotted_module):
                        hit = next((c for c in candidates if c.startswith(f"{guess}::")), None)
                        if hit:
                            target = hit
                            break
                if target is None and len(candidates) == 1:
                    target = candidates[0]
                if target:
                    resolved.add(target)

            if not resolved:
                continue
            test_key = f"{rel}:{lineno}"
            g.add_node("TestCase", test_key, source="ast-import-resolution", file=rel, line=lineno, function=name)
            for symbol_key in resolved:
                g.add_edge(
                    "TESTED_BY", "Symbol", symbol_key, "TestCase", test_key,
                    source="ast-import-resolution", confidence=0.95,
                    evidence_ref=f"{name} (line {lineno}) imports and calls a name resolving to {symbol_key}",
                )
    return g
