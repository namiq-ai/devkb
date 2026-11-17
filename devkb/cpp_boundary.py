"""C and C++ side of the cross-language records (ADR-DEVKB-009 §3): text in, `boundaries.Record`s out.

Reads the masked text of one file before `cpp_graph` frees it. Nothing here resolves a link (that is `boundaries.py`)
and nothing here writes the graph. It finds:
  * `extern "C"` exports (functions with C linkage and no `static`) and the `dlsym` lookups, which are dynamic;
  * a CPython `PyMethodDef` table: each entry exports `<module>.<name>` as `pyc-api`;
  * a pybind11 `m.def("name", &fn)` inside `PYBIND11_MODULE(mod, m)`: exports `mod.name` as `pybind11`;
  * `CONFIG_*` options and `DT_NODELABEL(label)` a file reads (R15), and Kconfig and devicetree declarations.
"""
from __future__ import annotations

import re
import subprocess
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from devkb.boundaries import Record
from devkb.cpp_symbols import FileRecords, Symbolic, _match_close, _split_top

_TABLE = re.compile(r"\bPyMethodDef\s+\w+\s*\[\s*\]\s*=\s*\{")
_ENTRY = re.compile(r"\{\s*(?P<q>\")[^\"]*\"\s*,\s*(?:\(\s*[\w\s*]+\)\s*)?(?P<fn>[A-Za-z_]\w*)\s*,")
_DLSYM = re.compile(r"\bdlsym\s*\(")
_ADDR = re.compile(r"&\s*((?:[A-Za-z_]\w*\s*::\s*)*[A-Za-z_]\w*)")
_PLAIN = re.compile(r"^\s*((?:[A-Za-z_]\w*\s*::\s*)*[A-Za-z_]\w*)\s*$")
_CONFIG = re.compile(r"\bCONFIG_[A-Za-z0-9_]+")
_NODELABEL = re.compile(r"\bDT_NODELABEL\s*\(\s*([A-Za-z_]\w*)\s*\)")

# find(name) -> (symbol key or None, overloaded) for the repository's free functions of that name
Finder = Callable[[str], "tuple[str | None, bool]"]


@dataclass
class FileBoundary:
    records: list[Record] = field(default_factory=list)
    explained: set[tuple[str, int, str]] = field(default_factory=set)      # (path, line, name): an export, not an indirect call
    reads: dict[tuple[str | None, str], int] = field(default_factory=dict)  # (owner qn or None, ConfigKey) -> first line


def _key(path: str, s: Symbolic) -> str:
    return f"{path}::{s.qn}"


def extract(path: str, rec: FileRecords, syms: dict[str, Symbolic], qn_of_def: list[str | None], find: Finder) -> FileBoundary:
    out = FileBoundary()
    m = rec.masked
    code, lits = m.code, m.literals
    lang = rec.language
    # extern "C" exports: functions with C linkage that are not static (kind flags are set by cpp_graph)
    for s in syms.values():
        if s.kind == "function" and s.linkage == "c":
            out.records.append(Record("export", s.short, "extern-c", path, s.line_start, _key(path, s), language=lang, kind="c-abi"))
    # dlsym: a lookup by a name the graph cannot follow (a literal one is also left unresolved in this slice)
    for d in rec.defs if "dlsym" in code else ():
        qn = qn_of_def[d.index] if 0 <= d.index < len(qn_of_def) else None
        if d.kind == "macro" or qn is None:
            continue
        for lo, hi in d.spans:
            for dm in _DLSYM.finditer(code, lo, hi):
                out.records.append(Record("import", "", "extern-c", path, m.line(dm.start()), f"{path}::{qn}", dynamic=True, language=lang))
    # PyMethodDef tables
    inits = [s.short[len("PyInit_"):] for s in syms.values() if s.kind == "function" and s.short.startswith("PyInit_")]
    for tm in _TABLE.finditer(code) if "PyMethodDef" in code else ():
        close = _match_close(code, tm.end() - 1, "{", "}")
        if close is None:
            continue
        for em in _ENTRY.finditer(code, tm.end(), close):
            fn, pyname = em.group("fn"), lits.get(em.start("q"))
            line = m.line(em.start("fn"))
            if not pyname:
                continue
            target = next((s for s in syms.values() if s.kind == "function" and s.short == fn), None)
            key, over = (_key(path, target), False) if target is not None else find(fn)
            if key is None:
                continue
            out.explained.add((path, line, fn))
            if len(inits) == 1:
                out.records.append(Record("export", f"{inits[0]}.{pyname}", "pyc-api", path, line, key, language=lang,
                                          kind="pyc-method", overloaded=over))
    # pybind11: m.def("name", &fn) in PYBIND11_MODULE(mod, m)
    for d in rec.defs:
        if d.kind != "macro" or d.macro_name != "PYBIND11_MODULE":
            continue
        args = [a.strip() for a in _split_top(d.macro_args)]
        if len(args) < 2 or not re.fullmatch(r"\w+", args[0]) or not re.fullmatch(r"\w+", args[1]):
            continue
        module, var = args
        for dm in re.finditer(r"\b" + re.escape(var) + r"\s*\.\s*def\s*\(", code[d.body[0]:d.body[1]]):
            open_i = d.body[0] + dm.end() - 1
            close = _match_close(code, open_i, "(", ")")
            if close is None:
                continue
            parts = _split_top(code[open_i + 1:close])
            if len(parts) < 2:
                continue
            q = code.find('"', open_i + 1, close)
            pyname = lits.get(q) if q >= 0 else None
            if not pyname:
                continue
            line = m.line(open_i)
            second = parts[1].strip()
            if second.startswith("["):
                out.records.append(Record("export", f"{module}.{pyname}", "pybind11", path, line, None, language=lang, kind="pybind11"))
                continue
            ref = _ADDR.search(second) or _PLAIN.match(second)
            if not ref:
                continue
            name = ref.group(1).replace(" ", "")
            if "::" in name:
                continue                      # `&K::go`: a class binding, not read (SPEC-DKB-002 story 6)
            key, over = find(name)
            if key is None:
                continue
            out.explained.add((path, m.line(open_i + 1 + code[open_i + 1:close].find(name)), name))
            out.explained.add((path, line, name))
            out.records.append(Record("export", f"{module}.{pyname}", "pybind11", path, line, key, language=lang,
                                      kind="pybind11", overloaded=over))
    _config_reads(rec, syms, qn_of_def, out)
    return out


def _config_reads(rec: FileRecords, syms: dict[str, Symbolic], qn_of_def: list[str | None], out: FileBoundary) -> None:
    """`CONFIG_FOO` and `DT_NODELABEL(x)` in masked code and conditional directives: READS from the function, else the file."""
    m = rec.masked
    if not ("CONFIG_" in m.code or "DT_NODELABEL" in m.code or any("CONFIG_" in b or "DT_NODELABEL" in b for _l, b in m.conds)):
        return                                  # nothing to read: skip building the function table
    funcs = sorted((d.line, d.line_end, qn_of_def[d.index]) for d in rec.defs
                   if d.kind in ("function", "method") and 0 <= d.index < len(qn_of_def) and qn_of_def[d.index])
    starts = [f[0] for f in funcs]

    def owner(line: int) -> str | None:
        i = bisect_right(starts, line) - 1
        return funcs[i][2] if i >= 0 and line <= funcs[i][1] else None

    def note(key: str, line: int) -> None:
        k = (owner(line), key)
        if k not in out.reads or line < out.reads[k]:
            out.reads[k] = line

    code = m.code
    if "CONFIG_" in code:
        for cm in _CONFIG.finditer(code):
            note("kconfig:" + cm.group(0), m.line(cm.start()))
    if "DT_NODELABEL" in code:
        for dm in _NODELABEL.finditer(code):
            note("devicetree:" + dm.group(1), m.line(dm.start()))
    for line, body in m.conds:
        if "CONFIG_" in body:
            for cm in _CONFIG.finditer(body):
                note("kconfig:" + cm.group(0), line)
        if "DT_NODELABEL" in body:
            for dm in _NODELABEL.finditer(body):
                note("devicetree:" + dm.group(1), line)


# ── Kconfig and devicetree declarations ────────────────────────────────────────
_KCONFIG_ENTRY = re.compile(r"^\s*(?:menuconfig|config|choice)\s+([A-Za-z0-9_]+)\s*(?:#.*)?$")
_DTS_LABEL = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*[A-Za-z_/@][\w@,.+\-/]*\s*\{")
_DTS_EXTS = (".dts", ".dtsi", ".overlay")
MAX_CONFIG_FILE_BYTES = 1024 * 1024


def is_kconfig_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name == "Kconfig" or name.startswith("Kconfig.") or name.lower().endswith(".kconfig")


def declarations(repo_root: Path) -> list[tuple[str, str, int]]:
    """(file, ConfigKey, line) for every Kconfig `config`/`menuconfig`/`choice` and every devicetree node label."""
    proc = subprocess.run(["git", "ls-files", "--recurse-submodules"], cwd=repo_root, capture_output=True, text=True, check=False)
    found: list[tuple[str, str, int]] = []
    for rel in sorted(set(proc.stdout.splitlines())):
        kc = is_kconfig_path(rel)
        if not kc and not rel.lower().endswith(_DTS_EXTS):
            continue
        try:
            p = repo_root / rel
            if p.stat().st_size > MAX_CONFIG_FILE_BYTES:
                continue
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if kc:
            for i, line in enumerate(text.splitlines(), 1):
                if "config" not in line and "choice" not in line:
                    continue                    # the entry pattern needs one of these words
                em = _KCONFIG_ENTRY.match(line)
                if em:
                    found.append((rel, "kconfig:CONFIG_" + em.group(1), i))
        else:
            text = re.sub(r"/\*.*?\*/", lambda x: re.sub(r"[^\n]", " ", x.group(0)), text, flags=re.S)
            for i, line in enumerate(text.splitlines(), 1):
                if ":" not in line or "{" not in line:
                    continue                    # a label needs `name: node {`; comments are only ever removed, so this is a superset
                lm = _DTS_LABEL.match(re.sub(r"//.*", "", line))
                if lm:
                    found.append((rel, "devicetree:" + lm.group(1), i))
    return found
