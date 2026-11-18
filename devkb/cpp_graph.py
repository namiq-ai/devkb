"""Writes C and C++ rows into the graph (ADR-DEVKB-008 §2, AD-2). The only module that does.

`add_to_graph(g, repo_root, error_sig_key)` runs extraction (`cpp_symbols`), resolution (`cpp_resolve`) and test-case
discovery (`test_discovery`), then writes `File`, `Symbol`, `DEFINED_IN`, `CALLS`, `RAISES`, `LOGS` and
`ErrorSignature` rows, and aggregates coverage over C/C++ symbols only, so a C++ unresolved call can never make a
Python symbol Incomplete. A repository with no C/C++ file adds nothing (its graph is byte-identical).
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Callable

from devkb import boundaries, cpp_boundary, cpp_resolve, cpp_symbols, py_boundaries, test_discovery
from devkb.cpp_symbols import Symbolic
from devkb.model import DevKBGraph

_SOURCE = "cpp-symbols"
_RAISE_CONF = {"cpp-throw": 0.9, "cpp-assert": 0.8}
_JNI = re.compile(r"^Java_\w+_\w+")
_LEADING_STEPS = re.compile(r"^(?:\.{1,2}/|/)+")


class _Includers:
    """Which languages include each header: the input of the `.h` rule (ADR-DEVKB-009 §2). One hop, `.c` and C++ includers only."""

    def __init__(self, headers: list[str]) -> None:
        self.headers = set(headers)
        self.by_base: dict[str, list[str]] = {}
        for h in headers:
            self.by_base.setdefault(h.rsplit("/", 1)[-1], []).append(h)
        self.langs: dict[str, list[str]] = {}

    def resolve(self, includer: str, include: str) -> list[str]:
        """The repository headers an `#include` names: next to the includer first, else every path ending the same way."""
        inc = include.strip()
        cands = self.by_base.get(inc.rsplit("/", 1)[-1], []) if inc else []
        if not cands:
            return []
        near = posixpath.normpath(posixpath.join(posixpath.dirname(includer), inc))
        if near in self.headers:
            return [near]
        norm = _LEADING_STEPS.sub("", posixpath.normpath(inc))  # `../`, `./`, `/` steps, not dots: `.gen/x.h` (#86)
        return [c for c in cands if c == norm or c.endswith("/" + norm)]

    def add(self, includer: str, language: str, include: str) -> None:
        for h in self.resolve(includer, include):
            self.langs.setdefault(h, []).append(language)


def _is_explained(t: tuple[str, str, str], explained: set[tuple[str, int, str]]) -> bool:
    """An unresolved indirect reference that is really a binding (PyMethodDef entry, pybind11 `m.def`): an export, not a mystery."""
    path, who, name = t
    if "@indirect:" not in who:
        return False
    try:
        return (path, int(who.rsplit("@indirect:", 1)[1]), name) in explained
    except ValueError:
        return False


def _boundary_kind(s: Symbolic) -> str | None:
    """`abi_exported`'s kind for a function another language may call by name (ADR-DEVKB-009 §3), else None."""
    if s.kind != "function" or s.linkage == "internal":
        return None
    if s.short.startswith("PyInit_"):
        return "pyinit"
    if _JNI.match(s.short):
        return "jni"
    return "c-abi" if s.linkage == "c" else None


def add_to_graph(g: DevKBGraph, repo_root: Path, error_sig_key: Callable[[str, str, str | None], str]) -> dict | None:
    """Add every C/C++ definition, call and error site; return the build report (None when there is no C/C++ file)."""
    files = cpp_symbols.list_files(repo_root)
    if not files:
        return None
    skipped: list[str] = []
    pending: list[tuple[str, cpp_symbols.FileRecords, dict[str, Symbolic], list[str | None]]] = []
    includers = _Includers([f for f in files if f.lower().endswith(".h")])
    # Pass 1: definitions, so the repository's symbol names are known. Headers come last: their language needs the
    # languages of the files that include them.
    for rel in sorted(files, key=lambda f: (f.lower().endswith(".h"), f)):
        path = repo_root / rel
        try:
            if path.stat().st_size > cpp_symbols.MAX_FILE_BYTES:
                skipped.append(rel)
                continue
            text = path.read_text(errors="replace")
        except OSError:
            skipped.append(rel)        # never silently dropped (architecture, State & cross-cutting)
            continue
        is_header = rel.lower().endswith(".h")
        rec = cpp_symbols.extract_file(rel, text, includers.langs.get(rel, []) if is_header else None)
        if not is_header:
            for inc in rec.includes:
                includers.add(rel, rec.language, inc)
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
    pending.sort(key=lambda t: t[0])
    # A C++ definition of a function that a guarded C header declared `extern "C"` has C linkage too (the first declaration decides).
    declared = {rel: cpp_symbols.c_declared_names(rec.masked) for rel, rec, _s, _q in pending if rec.consumed_by_cpp}
    if declared:
        for rel, rec, syms, _q in pending:
            if rec.language != "cpp" or rel.lower().endswith(".h"):
                continue
            hit: set[str] = set()
            for inc in rec.includes:
                for h in includers.resolve(rel, inc):
                    hit |= declared.get(h, set())
            for s in syms.values():
                if s.kind == "function" and s.linkage == "cpp" and s.short in hit:
                    s.linkage = "c"
    names = {s.short for _r, _rec, syms, _q in pending for s in syms.values() if s.kind != "test"}
    function_names = {s.short for _r, _rec, syms, _q in pending for s in syms.values() if s.kind in ("function", "method")}
    free_index: dict[str, list[tuple[str, Symbolic]]] = {}
    for rel, _rec, syms, _q in pending:
        for s in syms.values():
            if s.kind == "function":
                free_index.setdefault(s.short, []).append((rel, s))

    def find(name: str) -> tuple[str | None, bool]:
        """The repository's free function of that name: (Symbol key, whether the name picks more than one definition)."""
        cands = free_index.get(name, [])
        if not cands:
            return None, False
        return f"{cands[0][0]}::{cands[0][1].qn}", len(cands) > 1 or len(cands[0][1].def_indexes) > 1

    units: list[cpp_resolve.Unit] = []
    bnd: dict[str, cpp_boundary.FileBoundary] = {}
    for rel, rec, syms, qn_of_def in pending:      # pass 2: calls, errors, indirect references
        cpp_symbols.scan_bodies(rec, names, function_names)
        bnd[rel] = cpp_boundary.extract(rel, rec, syms, qn_of_def, find)
        rec.masked.code, rec.masked.literals = "", {}   # the text is not needed past this point; keep memory flat
        units.append(cpp_resolve.Unit(rel, rec, syms, qn_of_def))
    edges, unresolved, cross = cpp_resolve.resolve(units)
    reasons = cpp_resolve.incomplete_reasons(units)

    # Boundaries (ADR-DEVKB-009 §3): records from every extractor, one resolver.
    cpp_names = {s.short for u in units for s in u.syms.values() if s.kind == "function" and s.linkage == "cpp"}
    records: list[boundaries.Record] = [r for fb in bnd.values() for r in fb.records]
    for c in cross:
        records.append(boundaries.Record("import", c.name, "extern-c", c.path, c.line, f"{c.path}::{c.caller_qn}", language=c.language,
                                         blocked=c.language == "cpp" and c.name in cpp_names))
    exported_modules = {r.abi_name.split(".")[0] for r in records if r.direction == "export" and r.mechanism in ("pyc-api", "pybind11")}
    records += py_boundaries.extract(repo_root, modules=exported_modules)
    result = boundaries.resolve(records)
    linked = {(link.caller, link.callee.rsplit("::", 1)[-1]) for link in result.links if link.mechanism == "extern-c"}
    for c in cross:                 # a handed-over call nobody linked is still an unresolved call
        if (f"{c.path}::{c.caller_qn}", c.name) not in linked:
            unresolved.add((c.path, c.caller_qn, c.name))
    explained = {e for fb in bnd.values() for e in fb.explained}
    unresolved = {t for t in unresolved if not _is_explained(t, explained)}
    export_kind = {r.symbol: r.kind for r in records if r.direction == "export" and r.symbol and r.kind in ("pyc-method", "pybind11")}
    for link in result.links:
        edges.append(cpp_resolve.Edge(link.caller, link.callee, link.mechanism, link.confidence, link.evidence))
    indirect_names = {name for _rel, who, name in unresolved if "@indirect:" in who}

    by_name: dict[str, dict[str, int]] = {}
    for rel, _caller, name in unresolved:
        by_name.setdefault(name, {})
        by_name[name][rel] = by_name[name].get(rel, 0) + 1

    # Where an unattributed call to a method can hide besides the files that hold one: the file it is defined in and the
    # files of classes derived from its class (an unqualified call there) (#116).
    repo_classes = cpp_resolve.Repo(units)
    derived_files: dict[str, set[str]] = {}
    for cls_list in repo_classes.classes.values():
        for cls in cls_list:
            for anc in repo_classes.ancestors(cls):
                derived_files.setdefault(anc[1].qn, set()).add(cls[0])

    n_symbols = 0
    written: set[str] = set()
    for u in units:
        g.add_node("File", u.path, source=_SOURCE, language=u.rec.language, **({"consumed_by_cpp": True} if u.rec.consumed_by_cpp else {}))
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
                overload_count=max(1, len(s.def_indexes)), overload_lines=s.overload_lines,
                overload_spans=[list(x) for x in sorted(set(s.spans))[:20]], is_public=s.is_public,
                docstring_summary=None, decorators=[],
            )
            props["language"] = u.rec.language
            if s.kind in ("function", "method"):
                props["linkage"] = s.linkage
                kind = export_kind.get(key) or _boundary_kind(s)
                if kind:
                    props.update(abi_exported=True, boundary_kind=kind)
            if s.kind == "test":
                props["framework"] = s.framework
            else:
                files_of = by_name.get(s.short)
                if files_of:
                    ranked = sorted(files_of, key=lambda f: (-files_of[f], f))
                    if s.kind in ("function", "method"):
                        near = {u.path} | (derived_files.get(qn.rsplit(".", 1)[0], set()) if s.kind == "method" else set())
                        ranked = sorted(near) + [f for f in ranked if f not in near]
                        props["near_files"] = sorted(near)[:10]
                    props.update(unresolved_calls=sum(files_of.values()), unresolved_files=ranked[:20],
                                 unresolved_file_count=len(ranked))
                rs = set(reasons.get((u.path, qn), ()))
                rs |= result.reasons.get(key, set())
                if u.rec.language == "c" and s.short in indirect_names:
                    rs.add("indirect-reference")
                if skipped:
                    rs.add("unread-file")
                if rs:
                    props["incomplete_reasons"] = sorted(rs)
            if unattributed.get(qn):
                props["unattributed_errors"] = unattributed[qn]
            g.add_node("Symbol", key, source=_SOURCE, **props)
            written.add(key)
            g.add_edge("DEFINED_IN", "Symbol", key, "File", u.path, source=_SOURCE, confidence=1.0,
                       evidence_ref=f"{u.path}:{s.line_start}")
            n_symbols += 1
    for e in edges:
        g.add_edge("CALLS", "Symbol", e.caller, "Symbol", e.callee, source=e.source, confidence=e.confidence,
                   evidence_ref=e.evidence)
    foreign = {k: rs for k, rs in result.reasons.items() if k not in written}
    if foreign:                    # a Python function that calls into C and could not be linked: its own reason
        by_key = {n.natural_key: n for n in g.nodes("Symbol") if n.natural_key in foreign}
        for k, node in by_key.items():
            node.props["incomplete_reasons"] = sorted(set(node.props.get("incomplete_reasons") or ()) | foreign[k])
    _write_config_keys(g, repo_root, units, bnd)
    report = {"files": len(units), "symbols": n_symbols, "skipped": skipped[:100], "skipped_count": len(skipped)}
    g.meta["cpp"] = report
    g.meta["boundaries"] = {
        "links": len(result.links),
        "dynamic_lookups": len(result.dynamic),
        "unresolved": [{"file": r.file, "line": r.line, "abi_name": r.abi_name, "mechanism": r.mechanism, "reason": why}
                       for r, why in result.unlinked],
    }
    return report


def _write_config_keys(g: DevKBGraph, repo_root: Path, units: list[cpp_resolve.Unit], bnd: dict[str, cpp_boundary.FileBoundary]) -> None:
    """Kconfig and devicetree options as `ConfigKey` (R15): `READS` from the function or file that uses one, `DECLARES` from its file."""
    decl = cpp_boundary.declarations(repo_root)
    keys = {key for _f, key, _l in decl} | {k for fb in bnd.values() for (_o, k) in fb.reads}
    for key in sorted(keys):
        g.add_node("ConfigKey", key, source=_SOURCE, kind=key.split(":", 1)[0])
    for rel, key, line in decl:
        g.add_node("File", rel, source="cpp-config")
        g.add_edge("DECLARES", "File", rel, "ConfigKey", key, source="cpp-config", confidence=0.9, evidence_ref=f"{rel}:{line}")
    qn_known = {u.path: {s.qn for s in u.syms.values()} for u in units}
    lang_of = {u.path: u.rec.language for u in units}
    for rel, fb in sorted(bnd.items()):
        for (owner, key), line in sorted(fb.reads.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
            if owner and owner in qn_known.get(rel, ()):
                g.add_edge("READS", "Symbol", f"{rel}::{owner}", "ConfigKey", key, source="cpp-config", confidence=0.9,
                           evidence_ref=f"{rel}:{line}")
            else:
                g.add_node("File", rel, source=_SOURCE, language=lang_of[rel])
                g.add_edge("READS", "File", rel, "ConfigKey", key, source="cpp-config", confidence=0.9, evidence_ref=f"{rel}:{line}")
