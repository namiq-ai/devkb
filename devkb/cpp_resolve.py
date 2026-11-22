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

The C profile (ADR-DEVKB-009 §2) is its own, shorter order: no class, receiver or qualified rule exists in C.
  C1. same file  bare `N()`: the function `N` this file defines                                        -> cpp-same-file
  C2. linkage    bare `N()`: the only non-`static` function `N` in the repository, in a C file, not a
                 C library name                                                                       -> cpp-unique-free
  C3. otherwise  unresolved. A `p->read()` call is never linked: `read` is a field, not a method.
A call between C and C++ is never linked here: it is handed to the boundary resolver (`cross` records), which links
it only through `extern "C"` linkage and a unique name (`boundaries.py`).

Never: a bare call to another class's method, a C library name linked across files, a link made because a method
name is unique, or an edge to a name `#define`d as a macro.

Calls through repository macros (SPEC-DKB-004 F2, #118): a call to a macro `#define`d in the repository is expanded,
once per build, into the bare and qualified calls its body writes (nested repository macros followed to depth 4, the
macro's own parameters and `##`-pasted names left out). Each is resolved by the rules above as if written at the
invocation, from the invoking function's scope, and linked with source `cpp-macro`. A macro defined more than once
(`#if` variants) gives the union of its bodies, and its edges are marked `variant`. A macro the repository does not
define (a system header's) is never expanded.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from devkb.cpp_symbols import Call, FileRecords, Symbolic, _split_top, indirect_refs

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
class Cross:
    """A bare call that may cross the C/C++ line: the extern-c import record, before the resolver judges it."""
    path: str
    caller_qn: str
    name: str
    line: int
    language: str          # the caller file's language


@dataclass
class Edge:
    caller: str
    callee: str
    source: str
    confidence: float
    evidence: str
    variant: bool = False      # through a macro with several `#if` definitions: true under some configurations


_SOURCES = {
    "cpp-same-class": 0.8, "cpp-same-class-base": 0.7, "cpp-same-file": 0.8, "cpp-qualified": 0.9,
    "cpp-typed-receiver": 0.7, "cpp-typed-receiver-base": 0.6, "cpp-unique-free": 0.6,
    "cpp-macro": 0.5, "cpp-constructor": 0.7,
}
MACRO_DEPTH = 4
_NOT_CALLED = frozenset("if while for switch return sizeof defined do else case typeof __typeof__ alignof _Alignof "
                        "decltype static_assert _Static_assert __attribute__ __declspec".split())
_BODY_CALL = re.compile(r"(?<![\w.>#])(?:((?:[A-Za-z_]\w*\s*::\s*)+))?([A-Za-z_]\w*)\s*\(")


def _macro_calls(body: str) -> list[tuple[str, str]]:
    """(qualifier, name) of each call a `#define` body writes: not member calls, not the macro's parameters, not names
    pasted with `##`. A function-like macro's text starts with its parameter list (no space after the name)."""
    params: set[str] = set()
    pm = re.match(r"([\w\s,.]*)\)", body)
    if pm and body[:1] and not body[:1].isspace():
        params = {x.strip() for x in pm.group(1).split(",") if x.strip()}
        body = body[pm.end():]
    out = []
    for m in _BODY_CALL.finditer(body):
        name = m.group(2)
        if name in params or name in _NOT_CALLED or "##" in body[max(0, m.start() - 3):m.start()] + body[m.end(2):m.end(2) + 3]:
            continue
        out.append((re.sub(r"\s+", "", m.group(1) or "").rstrip(":"), name))
    return out


class Repo:
    """Indexes over all units; the lookups the rules need."""

    def __init__(self, units: list[Unit]) -> None:
        self.units = units
        self.macro_bodies: dict[str, list[str]] = {}
        self.by_qn: dict[str, list[tuple[str, Symbolic]]] = {}
        self.short_names: set[str] = set()
        self.free: dict[str, list[tuple[str, Symbolic]]] = {}
        self.classes: dict[str, list[tuple[str, object]]] = {}
        self.sym_suffix: dict[str, list[tuple[str, Symbolic]]] = {}
        self.class_suffix: dict[str, list[tuple[str, object]]] = {}
        self.namespaces: set[str] = set()
        self.macros: set[str] = set()
        self.definers: dict[str, set[str]] = {}    # macro name -> the files that `#define` it (#290)
        self.function_names: set[str] = set()
        self.non_ctor_names: set[str] = set()
        self.language: dict[str, str] = {u.path: u.rec.language for u in units}
        self.c_linkage: dict[str, list[tuple[str, Symbolic]]] = {}     # non-static functions with C linkage, by short name
        self.ns_paths: set[str] = set()        # every named namespace a file opens, as `a::b`
        self.aliases: set[str] = set()         # names a using-declaration, alias or typedef introduces somewhere
        for u in units:
            self.ns_paths |= getattr(u.rec.scanner, "ns_paths", set())
            self.aliases |= getattr(u.rec.scanner, "aliases", set())
            self.namespaces |= u.rec.namespaces
            self.macros |= u.rec.define_names
            for dn in u.rec.define_names:
                self.definers.setdefault(dn, set()).add(u.path)
            for dname, body, _line in (u.rec.masked.defines if u.rec.masked is not None else ()):
                self.macro_bodies.setdefault(dname, []).append(body)
            for qn, s in u.syms.items():
                self.by_qn.setdefault(qn, []).append((u.path, s))
                bits = qn.split(".")
                for i in range(len(bits)):
                    self.sym_suffix.setdefault(".".join(bits[i:]), []).append((u.path, s))
                if s.kind != "test":
                    self.short_names.add(s.short)
                if s.kind == "function":
                    self.free.setdefault(s.short, []).append((u.path, s))
                    if s.linkage == "c":
                        self.c_linkage.setdefault(s.short, []).append((u.path, s))
                if s.kind in ("function", "method"):
                    self.function_names.add(s.short)
                    owner = s.qn.rsplit(".", 2)[-2] if s.qn.count(".") >= 1 else ""
                    if not (s.kind == "method" and owner == s.short):
                        self.non_ctor_names.add(s.short)      # a function or a method that is not a constructor bears this name (#119)
            for c in u.rec.classes:
                self.classes.setdefault(c.qn, []).append((u.path, c))
                bits = c.qn.split(".")
                for i in range(1, len(bits)):
                    self.class_suffix.setdefault(".".join(bits[i:]), []).append((u.path, c))
        self._unit = {u.path: u for u in units}
        # #120: each symbol's declared return type (one, or None) and its argument counts, from its definitions
        self.ret: dict[str, tuple[str, str] | None] = {}
        self.arity: dict[str, list[tuple[int, float]]] = {}
        for u in units:
            for qn, s in u.syms.items():
                defs = [u.rec.defs[i] for i in s.def_indexes if 0 <= i < len(u.rec.defs)]
                rets = {d.ret for d in defs}
                self.ret[f"{u.path}::{qn}"] = rets.pop() if len(rets) == 1 else None
                self.arity[f"{u.path}::{qn}"] = [_arity(d.params) for d in defs]

    def member_type(self, cls: tuple[str, object], name: str, seen: set[str] | None = None):
        """The declared type of member `name` of a class, or of one of its in-repository bases; None when unknown."""
        seen = seen if seen is not None else set()
        if cls[1].qn + "@" + cls[0] in seen:
            return None
        seen.add(cls[1].qn + "@" + cls[0])
        if name in cls[1].members:
            return cls[1].members[name]
        for b in cls[1].bases:
            bc = self.class_by_type(b, cls[1].namespace)
            if bc is not None:
                t = self.member_type(bc, name, seen)
                if t is not None:
                    return t
        return None

    def by_arity(self, keys: list[str], argc: int) -> list[str]:
        """F5: the keys whose definitions accept `argc` arguments; all of them when argc is not known."""
        if argc < 0:
            return keys
        return [k for k in keys if any(lo <= argc <= hi for lo, hi in self.arity.get(k, [(0, float("inf"))]))]

    # macros --------------------------------------------------------------------
    def expand(self, name: str) -> list[tuple[str, str, bool]]:
        """(qualifier, name, variant) of the non-macro calls a call to repository macro `name` makes, nested macros
        followed to MACRO_DEPTH levels; computed once per macro."""
        cache = self.__dict__.setdefault("_expanded", {})
        if name not in cache:
            seen: dict[tuple[str, str], bool] = {}

            def walk(m: str, depth: int, variant: bool) -> None:
                bodies = self.macro_bodies.get(m, [])
                variant = variant or len(bodies) > 1
                for body in bodies:
                    for q, n in _macro_calls(body):
                        if not q and n in self.macros:
                            if depth < MACRO_DEPTH and n != m:
                                walk(n, depth + 1, variant)
                            continue
                        seen[(q, n)] = seen.get((q, n), True) and variant
            walk(name, 1, False)
            cache[name] = [(q, n, v) for (q, n), v in seen.items()]
        return cache[name]

    # macro scope (#290) --------------------------------------------------------
    def _include_edges(self) -> dict[str, set[str]]:
        """path -> the paths that include it (an `#include` names a repository file next to the includer first, else the one whose path ends the
        same way). Built once."""
        if "_rev" not in self.__dict__:
            paths = {u.path for u in self.units}
            by_base: dict[str, list[str]] = {}
            for p in paths:
                by_base.setdefault(p.rsplit("/", 1)[-1], []).append(p)
            rev: dict[str, set[str]] = {}
            for u in self.units:
                for inc in u.rec.includes:
                    inc = inc.strip()
                    cands = by_base.get(inc.rsplit("/", 1)[-1], []) if inc else []
                    if not cands:
                        continue
                    near = posixpath.normpath(posixpath.join(posixpath.dirname(u.path), inc))
                    norm = re.sub(r"^(?:\.{1,2}/|/)+", "", posixpath.normpath(inc))
                    for t in ([near] if near in paths else [c for c in cands if c == norm or c.endswith("/" + norm)]):
                        rev.setdefault(t, set()).add(u.path)
            self.__dict__["_rev"] = rev
        return self.__dict__["_rev"]

    def macro_scope(self, name: str) -> set[str]:
        """The files that see repository macro `name`: those that define it and those that include, at any depth, one that does."""
        cache = self.__dict__.setdefault("_scope", {})
        if name not in cache:
            rev = self._include_edges()
            seen = set(self.definers.get(name, ()))
            todo = list(seen)
            while todo:
                for f in rev.get(todo.pop(), ()):
                    if f not in seen:
                        seen.add(f)
                        todo.append(f)
            cache[name] = seen
        return cache[name]

    def sees(self, path: str, name: str, line: int = 0) -> bool:
        """Is `name`, written in `path` at `line`, a repository macro there: defined in that file or a header it includes, and not `#undef`ed
        earlier in it. A name that is also a function elsewhere stays a plain call in a file that never sees the macro (#290)."""
        if name not in self.macros:
            return False
        u = self._unit.get(path)
        if u is not None and u.rec.masked is not None and any(n == name and ln < line for n, ln in u.rec.masked.undefs):
            return False
        return path in self.macro_scope(name)

    # classes -------------------------------------------------------------------
    def class_by_type(self, t: str, from_ns: str | None = None) -> tuple[str, object] | None:
        """The one repository class a written type names, else None (ambiguous or not a repository class).

        `from_ns`: the namespace the type is written in. A name several namespaces' classes share is then looked up as
        C++ does, from that namespace outward (#93); without it, or when a nested class bears the name, it stays ambiguous."""
        absolute = t.replace(" ", "").startswith("::")
        parts = [p for p in t.replace(" ", "").lstrip(":").split("::") if p]
        lead: list[str] = []
        while len(parts) > 1 and parts[0] in self.namespaces:
            lead.append(parts[0])
            parts = parts[1:]
        if not parts:
            return None
        key = ".".join(parts)
        exact = self.classes.get(key, [])
        found = exact if exact else self.class_suffix.get(key, [])
        if len(found) == 1:
            return found[0]
        if from_ns is None or len(exact) < 2 or self.class_suffix.get(key) or parts[-1] in self.aliases:
            return None
        return self._lookup(exact, lead, "" if absolute else from_ns)

    def _lookup(self, cands: list[tuple[str, object]], lead: list[str], from_ns: str) -> tuple[str, object] | None:
        """C++ name lookup of a class among same-named `cands`: from `from_ns` outward, the first namespace that holds
        the name (or, for `a::K`, the first that sees a namespace `a`) decides; two classes there is None (#93). The
        callers give up first when a nested class, a using-declaration, an alias or a typedef bears the name: any of
        them may be what C++ finds, and none is a class here."""
        bits = from_ns.split("::") if from_ns else []
        for i in range(len(bits), -1, -1):
            level = bits[:i]
            if lead and "::".join(level + lead[:1]) not in self.ns_paths:
                continue
            ns = "::".join(level + lead)
            hits = [c for c in cands if c[1].namespace == ns]
            if hits or lead:
                return hits[0] if len(hits) == 1 else None
        return None

    def caller_class(self, path: str, chain: tuple[str, ...], from_ns: str | None = None) -> tuple[str, object] | None:
        """The class a method belongs to. `from_ns` (the method's `class_ns`) decides between same-named classes of
        different namespaces when the file layout does not (#93)."""
        if not chain:
            return None
        every = cands = self.classes.get(".".join(chain), [])
        if len(cands) > 1:
            same = [c for c in cands if c[0] == path]
            if not same:
                stem = path.rsplit(".", 1)[0].rsplit("/", 1)
                same = [c for c in cands if c[0].rsplit(".", 1)[0].rsplit("/", 1)[-1] == stem[-1]
                        and c[0].rsplit("/", 1)[0:-1] == (path.rsplit("/", 1)[0:-1])]
            cands = same
        if len(cands) == 1:
            return cands[0]
        if from_ns is None or len(every) < 2 or chain[0] in self.aliases:
            return None
        return self._lookup(every, [], from_ns)

    def method_on(self, cls: tuple[str, object], name: str, seen: set[str] | None = None, via_base: bool = False, argc: int = -1):
        """('hit', key, via_base) | ('declared',) | None: `name` on a class, else on its in-repository bases."""
        path, c = cls
        seen = seen or set()
        if c.qn + "@" + path in seen:
            return None
        seen.add(c.qn + "@" + path)
        found = [(p, s) for p, s in self.by_qn.get(c.qn + "." + name, []) if s.kind == "method"]
        if len(self.classes.get(c.qn, [])) > 1 and found:
            # a class name several namespaces share: only a method defined in this class's namespace is its own (#93)
            if any(s.class_ns is None for _p, s in found):
                return ("declared",)
            found = [(p, s) for p, s in found if s.class_ns == c.namespace]
        if len(found) > 1:              # F5: same-named targets narrowed by the call's argument count
            keep = set(self.by_arity([f"{p}::{s.qn}" for p, s in found], argc))
            found = [(p, s) for p, s in found if f"{p}::{s.qn}" in keep] or found
        if len(found) == 1:
            return ("hit", f"{found[0][0]}::{found[0][1].qn}", via_base)
        if found or name in c.methods:
            return ("declared",)
        for b in c.bases:
            bc = self.class_by_type(b, c.namespace)
            if bc is not None:
                r = self.method_on(bc, name, seen, True, argc)
                if r is not None:
                    return r
        return None

    def ancestors(self, cls: tuple[str, object], seen: set[str] | None = None) -> list[tuple[str, object]]:
        seen = seen if seen is not None else set()
        out = []
        for b in cls[1].bases:
            bc = self.class_by_type(b, cls[1].namespace)
            if bc is not None and bc[1].qn + "@" + bc[0] not in seen:
                seen.add(bc[1].qn + "@" + bc[0])
                out.append(bc)
                out.extend(self.ancestors(bc, seen))
        return out


def resolve(units: list[Unit]) -> tuple[list[Edge], set[tuple[str, str, str]], list[Cross]]:
    repo = Repo(units)
    edges: list[Edge] = []
    unresolved: set[tuple[str, str, str]] = set()
    cross: list[Cross] = []
    for u in units:
        is_c = not u.rec.cpp
        lang = u.rec.language
        by_def_free = {s.short: s for s in u.syms.values() if s.kind == "function"}
        free_count: dict[str, int] = {}
        for s in u.syms.values():
            if s.kind == "function":
                free_count[s.short] = free_count.get(s.short, 0) + 1
        for call, via in _with_expansions(u.rec.calls, repo, u.path):
            caller_qn = u.qn_of_def[call.caller]
            if caller_qn is None:
                continue
            if via is None and call.form != "construct" and repo.sees(u.path, call.name, call.line):
                # A macro use: never an edge. But a name that is also a repository function (a `#define` stub in an
                # `#else` branch, as Zephyr's net_if does) may be a real call under another configuration, so it is
                # counted, never ignored: a pack must not say Complete beside it.
                if call.name in repo.short_names:
                    unresolved.add((u.path, caller_qn, call.name))
                continue
            caller = u.syms.get(caller_qn)
            chain = caller.class_chain if caller is not None and caller.kind == "method" else ()
            if call.init and call.name not in repo.class_suffix and call.name not in repo.classes:
                # `: m(x)`: a member initialised, not a function called (#145). A member of a repository class type is built by that class's
                # constructor (#119); anything else is dropped. A base class's constructor stays a plain call, below.
                mt = None
                if chain and not is_c:
                    cls0 = repo.caller_class(u.path, chain, caller.class_ns if caller is not None else None)
                    mt = cls0[1].members.get(call.name) if cls0 is not None else None
                if mt is None or mt[1] != "":
                    continue
                call = Call(call.caller, mt[0].split("::")[-1], "construct", "::".join(mt[0].split("::")[:-1]), None, None, call.line, call.argc)
            if call.form == "bare" and not is_c and not call.init and (call.name in repo.class_suffix or call.name in repo.classes) \
                    and call.name not in repo.non_ctor_names and not (chain and call.name == chain[-1]):
                call = Call(call.caller, call.name, "construct", "", None, None, call.line, call.argc)   # `T(args)`: a temporary, a construction (#119)
            if call.form == "construct":
                if is_c:
                    continue
                caller_ns0 = caller.class_ns if caller is not None else None
                target = repo.class_by_type((call.qualifier + "::" if call.qualifier else "") + call.name, caller_ns0)
                if target is None:
                    if call.name in repo.class_suffix or call.name in repo.classes:
                        unresolved.add((u.path, caller_qn, call.name))   # several repository classes bear the name: no guess, and counted
                    continue                          # not a repository class (std::string, a typedef, ...): not ours to link, not counted
                r = repo.method_on(target, call.name, argc=call.argc)
                ckey0 = f"{u.path}::{caller_qn}"
                fits = True
                if r and r[0] == "hit" and call.argc >= 0:
                    ar = repo.arity.get(r[1]) or []
                    fits = not ar or any(lo <= call.argc <= hi for lo, hi in ar)      # a copy or move (`T x(other)`) fits no declared constructor
                if r and r[0] == "hit" and not r[2] and not fits:
                    continue                          # an implicit copy, move or conversion: no declared constructor is called (#119)
                if r and r[0] == "hit" and not r[2]:  # a constructor is not inherited: one found only through a base is not this class's
                    edges.append(Edge(ckey0, r[1], "cpp-constructor", _SOURCES["cpp-constructor"],
                                      f"{u.path}:{call.line}: {caller_qn} constructs {call.name}"))
                elif r:
                    unresolved.add((u.path, caller_qn, call.name))   # several constructors fit the argument count: left unresolved, and counted
                continue
            caller_ns = caller.class_ns if caller is not None else None
            ckey = f"{u.path}::{caller_qn}"
            n = call.name
            stop_unresolved = False

            def link(callee: str, source: str, detail: str) -> None:
                if via is not None:                   # a call the macro's body writes, made at the invocation (#118)
                    edges.append(Edge(ckey, callee, "cpp-macro", _SOURCES["cpp-macro"],
                                      f"{u.path}:{call.line}: {caller_qn} calls {detail} through macro {via[0]}", via[1]))
                    return
                edges.append(Edge(ckey, callee, source, _SOURCES[source], f"{u.path}::{caller_qn} calls {detail}"))

            def hand_over() -> bool:
                """A bare call to a name defined with C linkage in the other language: the boundary resolver decides."""
                if n in C_LIBRARY:
                    return False
                other = "cpp" if is_c else "c"
                if any(repo.language[p] == other for p, _s in repo.c_linkage.get(n, [])):
                    cross.append(Cross(u.path, caller_qn, n, call.line, lang))
                    return True
                return False

            if is_c:                                  # the C profile: linkage only (ADR-DEVKB-009 §2)
                if call.form == "bare":
                    if free_count.get(n) == 1:
                        link(f"{u.path}::{by_def_free[n].qn}", "cpp-same-file", n)
                        continue
                    if not free_count.get(n):
                        own = [(p, x) for p, x in repo.c_linkage.get(n, []) if repo.language[p] == "c"]
                        if len(own) == 1 and n not in C_LIBRARY:
                            link(f"{own[0][0]}::{own[0][1].qn}", "cpp-unique-free", n)
                            continue
                        if hand_over():
                            continue
                if n in repo.short_names:
                    unresolved.add((u.path, caller_qn, n))
                continue

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
                cls = repo.caller_class(u.path, chain, caller_ns) if chain else _fixture(repo, u.rec.defs[call.caller])
                if cls is not None:                 # a method's own class, or a TEST_F body's fixture (F4)
                    r = repo.method_on(cls, n, argc=call.argc)
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
                        if len(cands2) > 1:          # F5: narrowed by argument count
                            keep = set(repo.by_arity([f"{p}::{x.qn}" for p, x in cands2], call.argc))
                            cands2 = [(p, x) for p, x in cands2 if f"{p}::{x.qn}" in keep]
                        if len(cands2) == 1 and n not in C_LIBRARY and cands2[0][1].is_public and repo.language[cands2[0][0]] == "cpp":
                            link(f"{cands2[0][0]}::{cands2[0][1].qn}", "cpp-unique-free", n)
                            continue
                        if hand_over():
                            continue
            else:  # member
                cls = repo.caller_class(u.path, chain, caller_ns) if chain else _fixture(repo, u.rec.defs[call.caller])
                if call.chained is not None:       # `r.g().f()`: f on what g is declared to return (F4, one level)
                    irecv, g, irl = call.chained
                    inner = None
                    if irecv in ("", "this") and cls is not None:
                        inner = repo.method_on(cls, g)
                    else:
                        t = irl if isinstance(irl, tuple) else (cls[1].members.get(irecv) if irl is None and cls is not None else None)
                        tc = repo.class_by_type(t[0], caller_ns) if t is not None else None
                        inner = repo.method_on(tc, g) if tc is not None else None
                    rt = repo.ret.get(inner[1]) if inner and inner[0] == "hit" else None
                    target = repo.class_by_type(rt[0], caller_ns) if rt is not None else None
                    if target is not None:
                        r = repo.method_on(target, n, argc=call.argc)
                        if r and r[0] == "hit":
                            link(r[1], "cpp-typed-receiver-base" if r[2] else "cpp-typed-receiver", f"{g}().{n}")
                            continue
                if call.field_of is not None:      # `b.m.f()`: m's type, declared in the class of b (F4, one level)
                    base, brl, fld = call.field_of
                    bt = brl if isinstance(brl, tuple) else (cls[1].members.get(base) if brl is None and cls is not None else None)
                    bc = repo.class_by_type(bt[0], caller_ns) if bt is not None else None
                    mt = repo.member_type(bc, fld) if bc is not None else None
                    target = repo.class_by_type(mt[0], caller_ns) if mt is not None else None
                    if target is not None:
                        r = repo.method_on(target, n, argc=call.argc)
                        if r and r[0] == "hit":
                            link(r[1], "cpp-typed-receiver-base" if r[2] else "cpp-typed-receiver", f"{base}.{fld}.{n}")
                            continue
                if call.recv == "this" and cls is not None:
                    r = repo.method_on(cls, n, argc=call.argc)
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
                        target = repo.class_by_type(t[0], caller_ns)
                        if target is not None:
                            r = repo.method_on(target, n, argc=call.argc)
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
    return edges, unresolved, cross


def _arity(params: str) -> tuple[int, float]:
    """(required, most) arguments a parameter list accepts; `...` accepts any number."""
    parts = [p for p in _split_top(params or "") if p.strip() and p.strip() != "void"]
    if any("..." in p for p in parts):
        return (len([p for p in parts if "=" not in p and "..." not in p]), float("inf"))
    return (len([p for p in parts if "=" not in p]), len(parts))


def _fixture(repo: "Repo", d) -> tuple[str, object] | None:
    """F4: a `TEST_F(Fixture, Name)` / `TEST_P` body is a method of a subclass of Fixture."""
    if getattr(d, "kind", "") != "macro" or d.macro_name not in ("TEST_F", "TEST_P"):
        return None
    first = (_split_top(d.macro_args) or [""])[0].strip()
    return repo.class_by_type(first, d.namespace) if first else None


def _with_expansions(calls, repo: Repo, path: str = ""):
    """Each call, and after a call to a repository macro the calls its expansion makes there: (call, (macro, variant)). A macro is expanded
    only in the files that see it (#290)."""
    for call in calls:
        yield call, None
        if call.form != "construct" and call.name in repo.macro_bodies and (repo.sees(path, call.name, call.line) if path else call.name in repo.macros):
            for q, n, variant in repo.expand(call.name):
                yield Call(call.caller, n, "qualified" if q else "bare", q, None, None, call.line), (call.name, variant)


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
            cls = repo.caller_class(u.path, s.class_chain, s.class_ns)
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
