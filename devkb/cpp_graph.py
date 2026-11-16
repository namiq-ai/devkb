"""Writes C and C++ rows into the graph (ADR-DEVKB-008 §2, AD-2). The only module that does.

`add_to_graph(g, repo_root, error_sig_key)` runs extraction (`cpp_symbols`), resolution (`cpp_resolve`) and test-case
discovery (`test_discovery`), then writes `File`, `Symbol`, `DEFINED_IN`, `CALLS`, `RAISES`, `LOGS` and
`ErrorSignature` rows, and aggregates coverage over C/C++ symbols only, so a C++ unresolved call can never make a
Python symbol Incomplete. A repository with no C/C++ file adds nothing (its graph is byte-identical).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from devkb import cpp_resolve, cpp_symbols, test_discovery
from devkb.cpp_symbols import Symbolic
from devkb.model import DevKBGraph

_SOURCE = "cpp-symbols"
_RAISE_CONF = {"cpp-throw": 0.9, "cpp-assert": 0.8}


def add_to_graph(g: DevKBGraph, repo_root: Path, error_sig_key: Callable[[str, str, str | None], str]) -> dict | None:
    """Add every C/C++ definition, call and error site; return the build report (None when there is no C/C++ file)."""
    files = cpp_symbols.list_files(repo_root)
    if not files:
        return None
    skipped: list[str] = []
    pending: list[tuple[str, cpp_symbols.FileRecords, dict[str, Symbolic], list[str | None]]] = []
    for rel in files:          # pass 1: definitions, so the repository's symbol names are known
        path = repo_root / rel
        try:
            if path.stat().st_size > cpp_symbols.MAX_FILE_BYTES:
                skipped.append(rel)
                continue
            text = path.read_text(errors="replace")
        except OSError:
            skipped.append(rel)        # never silently dropped (architecture, State & cross-cutting)
            continue
        rec = cpp_symbols.extract_file(rel, text)
        syms = cpp_symbols.finalize(rec)
        qn_of_def: list[str | None] = [None] * len(rec.defs)
        for s in syms.values():
            for i in s.def_indexes:
                qn_of_def[i] = s.qn
        cases, _ = test_discovery.cxx_cases(rec.masked)
        for case in cases:
            if not case.body:
                continue
            d = next((d for d in rec.defs if d.kind == "macro" and d.macro_name == case.macro and d.macro_line == case.line), None)
            if d is None:
                continue
            s = syms.get(case.name)
            if s is None:
                s = syms[case.name] = Symbolic(case.name, case.name.rsplit(".", 1)[-1], "test", d.namespace, d.line, d.line_end,
                                               [d.line], True, False, (), [], case.framework)
            else:
                s.overload_lines = sorted(set(s.overload_lines) | {d.line})
            s.def_indexes.append(d.index)
            qn_of_def[d.index] = s.qn
        pending.append((rel, rec, syms, qn_of_def))
    names = {s.short for _r, _rec, syms, _q in pending for s in syms.values() if s.kind != "test"}
    function_names = {s.short for _r, _rec, syms, _q in pending for s in syms.values() if s.kind in ("function", "method")}
    units: list[cpp_resolve.Unit] = []
    for rel, rec, syms, qn_of_def in pending:      # pass 2: calls, errors, indirect references
        cpp_symbols.scan_bodies(rec, names, function_names)
        rec.masked.code, rec.masked.literals = "", {}   # the text is not needed past this point; keep memory flat
        units.append(cpp_resolve.Unit(rel, rec, syms, qn_of_def))
    edges, unresolved = cpp_resolve.resolve(units)
    reasons = cpp_resolve.incomplete_reasons(units)

    by_name: dict[str, dict[str, int]] = {}
    for rel, _caller, name in unresolved:
        by_name.setdefault(name, {})
        by_name[name][rel] = by_name[name].get(rel, 0) + 1

    n_symbols = 0
    for u in units:
        if not u.syms:
            continue
        g.add_node("File", u.path, source=_SOURCE)
        unattributed: dict[str, int] = {}
        for site in u.rec.errors:
            qn = u.qn_of_def[site.caller]
            if qn is None:
                continue
            if site.kind == "unattributed":
                unattributed[qn] = unattributed.get(qn, 0) + 1
                continue
            kind, verb = ("raised", "RAISES") if site.kind == "raises" else ("logged", "LOGS")
            sig = error_sig_key(kind, site.label, site.message)
            g.add_node("ErrorSignature", sig, source=_SOURCE, kind=kind, label=site.label, message_template=site.message,
                       status_code=None)
            g.add_edge(verb, "Symbol", f"{u.path}::{qn}", "ErrorSignature", sig, source=site.source,
                       confidence=_RAISE_CONF.get(site.source, 0.85), evidence_ref=f"{u.path}:{site.line}")
        for qn, s in sorted(u.syms.items()):
            key = f"{u.path}::{qn}"
            props: dict = dict(
                kind=s.kind, qualified_name=qn, namespace=s.namespace or None, line_start=s.line_start, line_end=s.line_end,
                overload_count=max(1, len(s.def_indexes)), overload_lines=s.overload_lines, is_public=s.is_public,
                docstring_summary=None, decorators=[],
            )
            if s.kind == "test":
                props["framework"] = s.framework
            else:
                files_of = by_name.get(s.short)
                if files_of:
                    ranked = sorted(files_of, key=lambda f: (-files_of[f], f))
                    props.update(unresolved_calls=sum(files_of.values()), unresolved_files=ranked[:20],
                                 unresolved_file_count=len(ranked))
                rs = set(reasons.get((u.path, qn), ()))
                if skipped:
                    rs.add("unread-file")
                if rs:
                    props["incomplete_reasons"] = sorted(rs)
            if unattributed.get(qn):
                props["unattributed_errors"] = unattributed[qn]
            g.add_node("Symbol", key, source=_SOURCE, **props)
            g.add_edge("DEFINED_IN", "Symbol", key, "File", u.path, source=_SOURCE, confidence=1.0,
                       evidence_ref=f"{u.path}:{s.line_start}")
            n_symbols += 1
    for e in edges:
        g.add_edge("CALLS", "Symbol", e.caller, "Symbol", e.callee, source=e.source, confidence=e.confidence,
                   evidence_ref=e.evidence)
    report = {"files": len(units), "symbols": n_symbols, "skipped": skipped[:100], "skipped_count": len(skipped)}
    g.meta["cpp"] = report
    return report
