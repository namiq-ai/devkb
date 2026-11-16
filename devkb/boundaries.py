"""Cross-language boundaries (ADR-DEVKB-009 §3, D8): extractors emit records, this one resolver matches them.

Pure: records in, links and failures out; no graph, no file. A record is never written to the graph.

An import is linked to an export only when
  * both records are in the repository (a name with no export is not a boundary: nothing is linked, nothing counted);
  * the export family matches (`extern-c`, `ctypes`, `cffi` imports meet C exports; `pyc-api`, `pybind11` imports meet
    module exports) and exactly one export bears the name;
  * that export has a defining Symbol.
Otherwise: two exports -> `ambiguous-abi-name` (marked on the exports); an export with no Symbol (a lambda) -> `lambda-binding`; a dynamic
import (a name that is not a literal, a `dlsym`) -> `dynamic-import`. None of them makes an edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MECHANISMS = ("extern-c", "ctypes", "cffi", "pyc-api", "pybind11")
CONFIDENCE = {"extern-c": 0.9, "ctypes": 0.8, "cffi": 0.8, "pyc-api": 0.8, "pybind11": 0.8}
_FAMILY = {"extern-c": "c", "ctypes": "c", "cffi": "c", "pyc-api": "module", "pybind11": "module"}
# Export mechanisms: a C ABI name is exported as `extern-c`; a module member as `pyc-api` or `pybind11`.


@dataclass
class Record:
    direction: str                 # export | import
    abi_name: str                  # the name on the wire; module exports are `<module>.<name>`
    mechanism: str                 # one of MECHANISMS
    file: str
    line: int
    symbol: str | None = None      # export: the defining Symbol key (None for a lambda); import: the calling Symbol key
    dynamic: bool = False          # import: the name is not a literal
    language: str = ""             # language of the file the record is written in
    kind: str = ""                 # export: boundary_kind of the defining Symbol
    overloaded: bool = False       # export: the target bears several overloads, so the name does not pick one
    blocked: bool = False          # import: the importing language has its own function of that name


@dataclass
class Link:
    caller: str
    callee: str
    mechanism: str
    confidence: float
    evidence: str                  # `<path>:<line>`


@dataclass
class Result:
    links: list[Link] = field(default_factory=list)
    reasons: dict[str, set[str]] = field(default_factory=dict)       # Symbol key -> incomplete_reasons to add
    unlinked: list[tuple[Record, str]] = field(default_factory=list)  # (import, reason) for an import that found an export and linked nothing
    dynamic: list[Record] = field(default_factory=list)              # dynamic imports, counted for the repository


def _reason(out: Result, key: str | None, reason: str) -> None:
    if key:
        out.reasons.setdefault(key, set()).add(reason)


def resolve(records: list[Record], unique: bool = True) -> Result:
    """Link imports to exports. `unique=False` is the seeded fault of the tests: it takes the first export of a name."""
    out = Result()
    exports: dict[tuple[str, str], list[Record]] = {}
    for r in records:
        if r.direction == "export":
            exports.setdefault((_FAMILY[r.mechanism], r.abi_name), []).append(r)
    seen: set[tuple[str, str, str]] = set()
    for imp in records:
        if imp.direction != "import":
            continue
        if imp.dynamic:
            out.dynamic.append(imp)
            _reason(out, imp.symbol, "dynamic-import")
            continue
        exs = exports.get((_FAMILY[imp.mechanism], imp.abi_name), [])
        if imp.mechanism == "extern-c":
            exs = [e for e in exs if e.mechanism == "extern-c"]
        if not exs or imp.blocked:
            continue
        if len(exs) > 1 and not unique:
            exs = exs[:1]
        if len(exs) > 1 or exs[0].overloaded:
            out.unlinked.append((imp, "ambiguous-abi-name"))
            for e in exs:
                _reason(out, e.symbol, "ambiguous-abi-name")
            continue
        ex = exs[0]
        if ex.symbol is None:
            out.unlinked.append((imp, "lambda-binding"))      # no function in the source: nothing to mark, the call is counted
            continue
        if imp.mechanism == "extern-c" and ex.language == imp.language:
            continue                      # same language: the language's own rules decide, never this resolver
        if not imp.symbol or imp.symbol == ex.symbol:
            continue
        mech = ex.mechanism if _FAMILY[imp.mechanism] == "module" else imp.mechanism
        ident = (imp.symbol, ex.symbol, mech)
        if ident in seen:
            continue
        seen.add(ident)
        out.links.append(Link(imp.symbol, ex.symbol, mech, CONFIDENCE[mech], f"{imp.file}:{imp.line}"))
    return out
