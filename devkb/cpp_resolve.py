"""Call resolution for C and C++ (ADR-DEVKB-008 §3, D2): prove a target or count the call as unresolved.

Records in, `(edges, unresolved)` out. The module reads no file and imports no graph. The order of rules is the only
order, and the first rule that proves a target wins; no later rule may guess:

  1. qualified   `Q::N()`        exactly one repository symbol `Q.N` (or free `N` in namespace `Q`)  -> cpp-qualified
  2. same class  bare `N()` in a method of K, or `this->N()`: `K.N`, then `N` on K's in-repository bases
  3. same file   bare `N()`: the free function `N` this file defines                                   -> cpp-same-file
  4. typed       `recv.N()` / `recv->N()`: recv's declared type (parameter, local, member) is a repository
                 class with the method                                                                 -> cpp-typed-receiver
  5. unique free bare `N()`: the only free function `N` in the repository, not a C library name       -> cpp-unique-free
  6. otherwise   a call to a name some repository symbol bears is *unresolved*; any other call is ignored.

Never: a bare call to another class's method, a C library name linked across files, a link made because a method
name is unique, or an edge for a name `#define`d as a macro.
"""
from __future__ import annotations

from dataclasses import dataclass

from devkb.cpp_symbols import FileRecords, Symbolic, indirect_refs

# The closed list of C library names that are never linked across files (ADR §3).
C_LIBRARY = frozenset(
    "exit abort _exit atexit memcpy memmove memset memcmp memchr strlen strcpy strncpy strcat strncat strcmp strncmp "
    "strchr strrchr strstr strtok strdup strerror printf fprintf sprintf snprintf vprintf vfprintf vsnprintf vsprintf "
    "sscanf scanf fscanf puts putchar fputs fputc fgets fgetc getc getchar fopen fclose fread fwrite fseek ftell "
    "fflush remove rename malloc calloc realloc free atoi atol atof strtol strtoul strtod qsort bsearch abs labs "
    "rand srand time clock getenv system assert isalpha isdigit isspace isalnum isupper islower toupper tolower "
    "setjmp longjmp signal raise open close read write unlink stat sleep usleep perror".split()
)
_EXTERNAL_ROOTS = frozenset({"std", "boost", "absl", "testing", "__gnu_cxx"})


@dataclass
class Unit:
    path: str
    rec: FileRecords
    syms: dict[str, Symbolic]
    qn_of_def: list[str | None]     # final qualified name of each def index (None: no symbol, e.g. a non-test macro)


@dataclass
class Edge:
    caller: str
    callee: str
    source: str
    confidence: float
    evidence: str


_SOURCES = {
    "cpp-same-class": 0.8, "cpp-same-class-base": 0.7, "cpp-same-file": 0.8, "cpp-qualified": 0.9,
    "cpp-typed-receiver": 0.7, "cpp-typed-receiver-base": 0.6, "cpp-unique-free": 0.6,
}


class Repo:
    """Indexes over all units; the lookups the rules need."""

    def __init__(self, units: list[Unit]) -> None:
        self.units = units
        self.by_qn: dict[str, list[tuple[str, Symbolic]]] = {}
        self.short_names: set[str] = set()
        self.free: dict[str, list[tuple[str, Symbolic]]] = {}
        self.classes: dict[str, list[tuple[str, object]]] = {}
        self.sym_suffix: dict[str, list[tuple[str, Symbolic]]] = {}
        self.class_suffix: dict[str, list[tuple[str, object]]] = {}
        self.namespaces: set[str] = set()
        self.macros: set[str] = set()
        self.function_names: set[str] = set()
        for u in units:
            self.namespaces |= u.rec.namespaces
            self.macros |= u.rec.define_names
            for qn, s in u.syms.items():
                self.by_qn.setdefault(qn, []).append((u.path, s))
                bits = qn.split(".")
                for i in range(len(bits)):
                    self.sym_suffix.setdefault(".".join(bits[i:]), []).append((u.path, s))
                if s.kind != "test":
                    self.short_names.add(s.short)
                if s.kind == "function":
                    self.free.setdefault(s.short, []).append((u.path, s))
                if s.kind in ("function", "method"):
                    self.function_names.add(s.short)
            for c in u.rec.classes:
                self.classes.setdefault(c.qn, []).append((u.path, c))
                bits = c.qn.split(".")
                for i in range(1, len(bits)):
                    self.class_suffix.setdefault(".".join(bits[i:]), []).append((u.path, c))
        self._unit = {u.path: u for u in units}

    # classes -------------------------------------------------------------------
    def class_by_type(self, t: str) -> tuple[str, object] | None:
        """The one repository class a written type names, else None (ambiguous or not a repository class)."""
        parts = [p for p in t.replace(" ", "").lstrip(":").split("::") if p]
        while len(parts) > 1 and parts[0] in self.namespaces:
            parts = parts[1:]
        if not parts:
            return None
        key = ".".join(parts)
        exact = self.classes.get(key, [])
        found = exact if exact else self.class_suffix.get(key, [])
        return found[0] if len(found) == 1 else None

    def caller_class(self, path: str, chain: tuple[str, ...]) -> tuple[str, object] | None:
        if not chain:
            return None
        cands = self.classes.get(".".join(chain), [])
        if len(cands) > 1:
            same = [c for c in cands if c[0] == path]
            if not same:
                stem = path.rsplit(".", 1)[0].rsplit("/", 1)
                same = [c for c in cands if c[0].rsplit(".", 1)[0].rsplit("/", 1)[-1] == stem[-1]
                        and c[0].rsplit("/", 1)[0:-1] == (path.rsplit("/", 1)[0:-1])]
            cands = same
        return cands[0] if len(cands) == 1 else None

    def method_on(self, cls: tuple[str, object], name: str, seen: set[str] | None = None, via_base: bool = False):
        """('hit', key, via_base) | ('declared',) | None: `name` on a class, else on its in-repository bases."""
        path, c = cls
        seen = seen or set()
        if c.qn + "@" + path in seen:
            return None
        seen.add(c.qn + "@" + path)
        found = [(p, s) for p, s in self.by_qn.get(c.qn + "." + name, []) if s.kind == "method"]
        if len(found) == 1:
            return ("hit", f"{found[0][0]}::{found[0][1].qn}", via_base)
        if found or name in c.methods:
            return ("declared",)
        for b in c.bases:
            bc = self.class_by_type(b)
            if bc is not None:
                r = self.method_on(bc, name, seen, True)
                if r is not None:
                    return r
        return None

    def ancestors(self, cls: tuple[str, object], seen: set[str] | None = None) -> list[tuple[str, object]]:
        seen = seen if seen is not None else set()
        out = []
        for b in cls[1].bases:
            bc = self.class_by_type(b)
            if bc is not None and bc[1].qn + "@" + bc[0] not in seen:
                seen.add(bc[1].qn + "@" + bc[0])
                out.append(bc)
                out.extend(self.ancestors(bc, seen))
        return out


def resolve(units: list[Unit]) -> tuple[list[Edge], set[tuple[str, str, str]]]:
    repo = Repo(units)
    edges: list[Edge] = []
    unresolved: set[tuple[str, str, str]] = set()
    for u in units:
        by_def_free = {s.short: s for s in u.syms.values() if s.kind == "function"}
        free_count: dict[str, int] = {}
        for s in u.syms.values():
            if s.kind == "function":
                free_count[s.short] = free_count.get(s.short, 0) + 1
        for call in u.rec.calls:
            caller_qn = u.qn_of_def[call.caller]
            if caller_qn is None:
                continue
            if call.name in repo.macros:
                # A macro use: never an edge. But a name that is also a repository function (a `#define` stub in an
                # `#else` branch, as Zephyr's net_if does) may be a real call under another configuration, so it is
                # counted, never ignored: a pack must not say Complete beside it.
                if call.name in repo.short_names:
                    unresolved.add((u.path, caller_qn, call.name))
                continue
            caller = u.syms.get(caller_qn)
            chain = caller.class_chain if caller is not None and caller.kind == "method" else ()
            ckey = f"{u.path}::{caller_qn}"
            n = call.name
            stop_unresolved = False

            def link(callee: str, source: str, detail: str) -> None:
                edges.append(Edge(ckey, callee, source, _SOURCES[source], f"{u.path}::{caller_qn} calls {detail}"))

            if call.form == "qualified":
                parts = [p for p in call.qualifier.split("::") if p]
                root = parts[0] if parts else ""
                if root in _EXTERNAL_ROOTS or (root not in repo.namespaces and root not in repo.short_names):
                    continue                      # a library or unknown root: ignored, not counted
                kept = [p for p in parts if p not in repo.namespaces] or []
                key = ".".join(kept + [n]) if kept else None
                cands: dict[str, tuple[str, Symbolic]] = {}
                if key:
                    for p, s in repo.sym_suffix.get(key, []):
                        cands[f"{p}::{s.qn}"] = (p, s)
                nsq = "::".join(p for p in parts if p in repo.namespaces)
                if nsq and not kept:
                    for p, s in repo.free.get(n, []):
                        if s.namespace == nsq or s.namespace.endswith("::" + nsq):
                            cands[f"{p}::{s.qn}"] = (p, s)
                if len(cands) == 1:
                    link(next(iter(cands)), "cpp-qualified", f"{call.qualifier}::{n}")
                    continue
            elif call.form == "bare":
                if chain:
                    cls = repo.caller_class(u.path, chain)
                    if cls is not None:
                        r = repo.method_on(cls, n)
                        if r and r[0] == "hit":
                            link(r[1], "cpp-same-class-base" if r[2] else "cpp-same-class", n)
                            continue
                        if r:
                            stop_unresolved = True
                if not stop_unresolved:
                    if free_count.get(n) == 1:
                        s = by_def_free[n]
                        link(f"{u.path}::{s.qn}", "cpp-same-file", n)
                        continue
                    if not free_count.get(n):
                        cands2 = repo.free.get(n, [])
                        if len(cands2) == 1 and n not in C_LIBRARY and cands2[0][1].is_public:
                            link(f"{cands2[0][0]}::{cands2[0][1].qn}", "cpp-unique-free", n)
                            continue
            else:  # member
                cls = repo.caller_class(u.path, chain) if chain else None
                if call.recv == "this" and cls is not None:
                    r = repo.method_on(cls, n)
                    if r and r[0] == "hit":
                        link(r[1], "cpp-same-class-base" if r[2] else "cpp-same-class", n)
                        continue
                elif call.recv and call.recv != "this":
                    t = None
                    if isinstance(call.recv_local, tuple):
                        t = call.recv_local
                    elif call.recv_local is None and cls is not None:
                        t = cls[1].members.get(call.recv)
                    if t is not None:
                        target = repo.class_by_type(t[0])
                        if target is not None:
                            r = repo.method_on(target, n)
                            if r and r[0] == "hit":
                                link(r[1], "cpp-typed-receiver-base" if r[2] else "cpp-typed-receiver", n)
                                continue
            if n in repo.short_names:
                unresolved.add((u.path, caller_qn, n))
        # indirect references (callbacks, `&f`, initialisers, macro bodies) are calls the graph cannot follow
        for name, line, owner in indirect_refs(u.rec, repo.function_names):
            if name in repo.macros and name not in repo.function_names:
                continue
            who = u.qn_of_def[owner] if owner >= 0 and u.qn_of_def[owner] else "<file>"
            unresolved.add((u.path, f"{who}@indirect:{line}", name))
    return edges, unresolved


def incomplete_reasons(units: list[Unit]) -> dict[tuple[str, str], set[str]]:
    """`dynamic-dispatch` and `implicit-call` per (path, qualified name) (ADR §2, §4)."""
    repo = Repo(units)
    out: dict[tuple[str, str], set[str]] = {}
    derived: dict[str, set[str]] = {}
    for u in units:
        for c in u.rec.classes:
            for a in repo.ancestors((u.path, c)):
                derived.setdefault(a[1].qn + "@" + a[0], set()).add(c.qn + "@" + u.path)
    cls_by_id = {c.qn + "@" + p: (p, c) for lst in repo.classes.values() for p, c in lst}
    for u in units:
        for qn, s in u.syms.items():
            reasons = out.setdefault((u.path, qn), set())
            if s.short.startswith("operator") or s.short.startswith("~") or (s.kind == "method" and s.class_chain and s.short == s.class_chain[-1]):
                reasons.add("implicit-call")
            if s.kind != "method" or not s.class_chain:
                continue
            cls = repo.caller_class(u.path, s.class_chain)
            if cls is None:
                continue
            if s.virtual or cls[1].methods.get(s.short):
                reasons.add("dynamic-dispatch")
            if any(s.short in a[1].methods for a in repo.ancestors(cls)):
                reasons.add("dynamic-dispatch")
            for did in derived.get(cls[1].qn + "@" + cls[0], ()):
                if s.short in cls_by_id[did][1].methods:
                    reasons.add("dynamic-dispatch")
    return out
