"""Read tools: ask the graph what agents otherwise grep for (SPEC-DKB-003, ADR-DEVKB-010).

  symbol(query)       where a name is defined, with its exact range and, on request, its source
  outline(path)       the shape of a file or directory: symbols in order with nesting, plus the import lines
  uses(name)          where a name appears, grouped by the symbol that contains each use (a text search, not references)
  search_docs(query)  where the documentation says something, with the heading each hit sits under

Language-agnostic: they read the Symbol nodes every extractor writes (`kind`, `line_start`, `line_end`) and the working tree.
What differs per language is only whether a symbol's end line is real. TypeScript, JavaScript and Odoo XML symbols store
`line_end == line_start` today, so the tools say "end unknown" for them and never invent a range.

Each tool returns a dict (tested, and the shape the MCP server and the CLI render) and `render_*` turns it into the compact
text an agent reads. Output is capped by design; what was cut is always stated.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import defaultdict
from pathlib import Path

SIMILAR_MIN = 55          # on a 0-60 scale (edit-similarity ratio >= 0.917): below it a fuzzy hit is a suggestion, not a match
MAX_SOURCE = 80           # lines of source a symbol call returns unless asked for more
HARD_SOURCE = 200
BUDGET = 6000             # bytes per text reply (ADR-DEVKB-010 §2); whole lines are cut from the end and the cut is stated
LANG = {".py": "Python", ".pyi": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
        ".mjs": "JavaScript", ".cjs": "JavaScript", ".cs": "C#", ".c": "C", ".h": "C or C++", ".cc": "C++", ".cpp": "C++",
        ".cxx": "C++", ".hpp": "C++", ".hh": "C++", ".hxx": "C++", ".xml": "Odoo XML", ".vue": "Vue"}
APPROX_WINDOW = 40        # lines shown from the start of a symbol whose end is unknown
START_ONLY = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".xml")   # extractors that do not store an end line
CXX_SUFFIX = (".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp")
DOC_SUFFIX = (".md", ".markdown", ".rst", ".txt", ".adoc")
NOT_CODE = (".md", ".markdown", ".rst", ".txt", ".adoc", ".lock", ".json", ".svg", ".min.js", ".map", ".csv", ".ipynb",
            ".jsonl", ".ndjson", ".tsv", ".log")   # data files too (dogfood D4, #40: benchmark transcripts drowned `uses`)
REGEXY = re.compile(r"[\^$+()\[\]{}|\\]|\.\*|\.\+")
KINDS = {"function", "method", "class", "enum", "struct", "interface", "test"}
IMPORT_RE = {
    ".py": r"^\s*(from\s+\S+\s+import\s|import\s+\S)", ".pyi": r"^\s*(from\s+\S+\s+import\s|import\s+\S)",
    ".ts": r"^\s*(import\s|export\s+\*?\s*from\s|.*\brequire\()", ".tsx": r"^\s*(import\s|.*\brequire\()",
    ".js": r"^\s*(import\s|.*\brequire\()", ".jsx": r"^\s*(import\s|.*\brequire\()", ".mjs": r"^\s*import\s",
    ".cs": r"^\s*using\s+[\w.]+;", ".c": r"^\s*#\s*include\b", ".h": r"^\s*#\s*include\b", ".cc": r"^\s*#\s*include\b",
    ".cpp": r"^\s*#\s*include\b", ".hpp": r"^\s*#\s*include\b", ".cxx": r"^\s*#\s*include\b", ".hh": r"^\s*#\s*include\b",
}


def _module_of(path: str) -> str:
    """A file's dotted module path, lower case: `devkb/cli.py` -> `devkb.cli`, `pkg/__init__.py` -> `pkg`."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", path).replace("/", ".").lower()
    return stem[: -len(".__init__")] if stem.endswith(".__init__") else stem


def repo_path(path: str) -> str:
    """A path as the graph keys it: without leading `./` and `/`. Not `lstrip("./")`, which strips characters and so
    took the dot off `.github/...` (#54)."""
    path = path.strip()
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def range_state(path: str, ls: int | None, le: int | None) -> str:
    """exact: the graph holds a real end line. end unknown: the language's extractor stores none. one line: a real one-line body."""
    if ls and le and le > ls:
        return "exact"
    return "end unknown" if path.endswith(START_ONLY) else "one line"


def words_of(s: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


class ReadTools:
    """Bound to one ProcessAPI; builds its name tables on first use (a few ms per ten thousand symbols)."""

    def __init__(self, api) -> None:
        self.api = api
        self.idx = api.idx
        self.root: Path = api.root
        self._lines: dict[str, list[str]] = {}
        self._skipped: dict[str, str] | None = None
        sym = [i for i, t in enumerate(self.idx.types) if t == "Symbol"]
        self.ids = sym
        self.file = {i: self.idx.keys[i].split("::", 1)[0] for i in sym}
        self.qual = {i: self.idx.keys[i].split("::", 1)[1] if "::" in self.idx.keys[i] else self.idx.keys[i] for i in sym}
        self.short = {i: self.qual[i].rsplit(".", 1)[-1] for i in sym}
        self._tri: dict[str, set[int]] | None = None
        self._names: list[str] | None = None
        self._by_name: dict[str, list[int]] | None = None

    # ── files ─────────────────────────────────────────────────────────────
    def lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            try:
                self._lines[rel] = (self.root / rel).read_text(errors="replace").splitlines()
            except OSError:
                self._lines[rel] = []
        return self._lines[rel]

    def resolve_file(self, path: str) -> tuple[str | None, list[str]]:
        """A tracked path, or the one tracked file that ends with it; else the candidates."""
        path = repo_path(path)
        known = set(self.idx.sym_by_file) | {k for (t, k) in self.idx.by_key if t == "File"}
        if path in known:
            return path, []
        hits = sorted(f for f in known if f.endswith("/" + path) or f == path)
        return (hits[0], []) if len(hits) == 1 else (None, hits[:8])

    # ── name resolution ───────────────────────────────────────────────────
    def _tables(self) -> None:
        if self._by_name is not None:
            return
        by: dict[str, list[int]] = defaultdict(list)
        for i in self.ids:
            by[self.short[i].lower()].append(i)
        self._by_name = dict(by)
        self._names = sorted(by)
        tri: dict[str, set[int]] = defaultdict(set)
        for n, name in enumerate(self._names):
            for j in range(len(name) - 2):
                tri[name[j:j + 3]].add(n)
        self._tri = dict(tri)

    def _rank_key(self, i: int, score: float, exact_case: bool = True):
        """Best tier score first; among equals production before tests, shallower qualified name, more callers, the
        spelling the query used, then path and line. Case alone never lifts test code above production code."""
        path = self.file[i]
        return (-score, self.api._is_test(path), self.qual[i].count("."), -self.api._caller_count(i), 0 if exact_case else 1, path,
                self.idx.props[i].get("line_start") or 0)

    def resolve(self, query: str, kind: str = "", under: str = "", limit: int = 8, tests: bool = True) -> dict:
        """Tiered, stops at the first tier with hits: exact, qualified, suffix, glob, regex, prefix/substring/words, then
        edit similarity (only a hit at SIMILAR_MIN or above is a match; below it the closest names are suggestions)."""
        self._tables()
        q = query.strip()
        want_file = ""
        if "::" in q:
            left, right = q.rsplit("::", 1)
            if "/" in left or re.search(r"\.[A-Za-z0-9]{1,5}$", left):
                want_file, q = repo_path(left), right
        q = q.replace("::", ".").replace("#", ".")
        ql = q.lower()
        rx = None
        if ql.startswith("re:") or REGEXY.search(q):
            try:
                rx = re.compile(q[3:] if ql.startswith("re:") else q, re.I)
            except re.error as e:
                return {"query": query, "error": f"bad regular expression: {e}"}
        pool = [i for i in self.ids
                if (not kind or self.idx.props[i].get("kind") == kind)
                and (not under or self.file[i].startswith(under))
                and (not want_file or self.file[i] == want_file or self.file[i].endswith("/" + want_file))
                and (tests or not self.api._is_test(self.file[i]))]
        poolset = set(pool)

        def collect(pred, score_of):
            return {i: score_of(i) for i in pool if pred(i)}

        tiers = []
        if rx is None:
            tiers.append(("exact", lambda: collect(lambda i: self.short[i].lower() == ql or self.qual[i].lower() == ql, lambda i: 100)))
            if "." in ql:
                tiers.append(("suffix", lambda: collect(lambda i: self.qual[i].lower().endswith("." + ql), lambda i: 90)))
                # `module.name` as code writes it (`cli.main`, `devkb.cli.main`): the file's dotted path, then the
                # qualified name (#100)
                tiers.append(("module", lambda: collect(
                    lambda i: ("." + _module_of(self.file[i]) + "." + self.qual[i].lower()).endswith("." + ql),
                    lambda i: 88)))
                # `ns::A::f` where the graph keeps `A.f`: drop leading qualifiers (namespaces), keeping `Class.method` at least
                parts = ql.split(".")
                for n in range(1, len(parts) - 1):
                    rest = ".".join(parts[n:])
                    tiers.append(("suffix", lambda rest=rest: collect(lambda i: self.qual[i].lower() == rest or self.qual[i].lower().endswith("." + rest), lambda i: 85)))
            if "*" in q or "?" in q:
                tiers.append(("glob", lambda: collect(lambda i: fnmatch.fnmatchcase(self.short[i].lower(), ql) or fnmatch.fnmatchcase(self.qual[i].lower(), ql), lambda i: 80)))
        else:
            tiers.append(("regex", lambda: collect(lambda i: bool(rx.search(self.short[i]) or rx.search(self.qual[i])), lambda i: 85 if rx.fullmatch(self.short[i]) else 75)))
        if rx is None:
            tiers.append(("prefix", lambda: collect(lambda i: self.short[i].lower().startswith(ql), lambda i: 70 + 10 * len(ql) / max(1, len(self.short[i])))))
            tiers.append(("substring", lambda: collect(lambda i: ql in self.short[i].lower() or ql in self.qual[i].lower(), lambda i: 50 + 10 * len(ql) / max(1, len(self.short[i])))))
            qw = set(words_of(q))
            if len(qw) >= 1 and (" " in q or "_" in q or re.search(r"[a-z][A-Z]", q)):
                tiers.append(("words", lambda: collect(lambda i: qw <= set(words_of(self.short[i])), lambda i: 55 + 5 * len(qw) / max(1, len(words_of(self.short[i]))))))
        for how, run in tiers:
            hit = run()
            if hit:
                order = sorted(hit, key=lambda i: self._rank_key(i, hit[i], self.short[i] == q or self.qual[i] == q))
                return self._reply(query, "qualified" if how == "exact" and "." in q and not any(self.short[i].lower() == ql for i in hit) else how, order, hit, limit)
        # similarity fallback
        cand_names: dict[int, int] = defaultdict(int)
        for j in range(len(ql) - 2):
            for n in self._tri.get(ql[j:j + 3], ()):
                cand_names[n] += 1
        scored = []
        for n, _ in sorted(cand_names.items(), key=lambda kv: -kv[1])[:600]:
            name = self._names[n]
            ratio = difflib.SequenceMatcher(None, ql, name).ratio()
            if ratio >= 0.6:
                scored.append((60 * ratio, name))
        scored.sort(reverse=True)
        good = [(s, n) for s, n in scored if s >= SIMILAR_MIN]
        if good:
            hit = {}
            for s, name in good[:6]:
                for i in self._by_name[name]:
                    if i in poolset:
                        hit[i] = s
            if hit:
                order = sorted(hit, key=lambda i: self._rank_key(i, hit[i]))
                return self._reply(query, "similar", order, hit, limit)
        sugg = []
        for sc, name in scored[:5]:
            ids = [i for i in self._by_name.get(name, []) if i in poolset]
            if ids:
                best = sorted(ids, key=lambda i: self._rank_key(i, sc))[0]
                sugg.append({"name": self.short[best], "path": self.file[best], "score": round(sc)})
        return {"query": query, "how": None, "n": 0, "matches": [], "suggestions": sugg}

    def _reply(self, query, how, order, hit, limit) -> dict:
        rows = []
        for i in order[:limit]:
            p = self.idx.props[i]; f = self.file[i]; ls, le = p.get("line_start"), p.get("line_end")
            rows.append({"i": i, "k": self.idx.keys[i], "kind": p.get("kind"), "ls": ls, "le": le, "range": range_state(f, ls, le),
                         "doc": (p.get("docstring_summary") or "")[:90], "callers": self.api._caller_count(i),
                         "self_call": self.api._calls_itself(i), "value_refs": int(p.get("value_ref_count") or 0), "refs": int(p.get("ref_count") or 0),
                         # calls under this name the resolver left unattributed: the count above is a lower bound (#87)
                         "unresolved": int(p.get("unresolved_calls") or 0),
                         "shared_by": len(self.idx.short.get(self.short[i], [])),
                         "how": how if how != "similar" else f"similar {hit[i] / 60:.2f}"})
        return {"query": query, "how": how, "n": len(order), "matches": rows}

    # ── symbol ────────────────────────────────────────────────────────────
    def key_uses(self, name: str, under: str = "") -> list[dict]:
        """#148: where a string key is written and read, grouped by function: `d["k"]`, `d.get("k")`, `{"k": v}`.
        Recorded by the Python extractor on the function's Symbol (a File for module-level code)."""
        out = []
        for i, p in enumerate(self.idx.props):
            r, w = (p.get("key_reads") or {}).get(name), (p.get("key_writes") or {}).get(name)
            if not (r or w):
                continue
            f, _, q = self.idx.keys[i].partition("::")
            if under and not f.startswith(under):
                continue
            out.append({"f": f, "in": q or None, "reads": r or [], "writes": w or []})
        return sorted(out, key=lambda x: (self.api._is_test(x["f"]), x["f"], x["in"] or ""))

    def symbol(self, query: str, source: bool = False, kind: str = "", under: str = "", limit: int = 8,
               lines: int = MAX_SOURCE, tests: bool = True) -> dict:
        r = self.resolve(query, kind, under, limit, tests)
        if r.get("error"):
            return r
        if not r["matches"]:
            if not kind and re.fullmatch(r"[A-Za-z_]\w*", query.strip()):
                ku = self.key_uses(query.strip(), under)
                if ku:
                    r["key_uses"] = ku
            return r
        max_lines = max(1, min(int(lines), HARD_SOURCE))
        capped = int(lines) > HARD_SOURCE
        for n, m in enumerate(r["matches"]):
            f = m["k"].split("::", 1)[0]; ln = self.lines(f); ls = m["ls"] or 0
            short = m["k"].rsplit(".", 1)[-1].split("::")[-1]
            sig = ln[ls - 1].strip() if 0 < ls <= len(ln) else ""
            if ls and short not in sig:                       # the graph is older than the file: re-anchor if we can
                for d in sorted(range(-150, 151), key=abs):
                    j = ls - 1 + d
                    if 0 <= j < len(ln) and short in ln[j] and re.search(r"\b(def|class|function|func|fn|struct|enum|interface|static|public|private|protected|void|async|const|let|var)\b|\)\s*[:{]?\s*$", ln[j]):
                        m["moved"] = d; sig = ln[j].strip(); ls += d
                        if m["le"] and m["le"] > m["ls"]:
                            m["le"] += d
                        m["ls"] = ls
                        break
                else:
                    m["moved"] = "not found near the recorded line; the graph is stale for this file"
            m["sig"] = sig[:140]
            m.pop("i", None)
            if source and n == 0 and ls:
                m["source"] = self._source(f, ln, m, max_lines)
                if capped:
                    m["source"]["capped"] = HARD_SOURCE
        return r

    def _source(self, f, ln, m, max_lines) -> dict:
        ls, le = m["ls"], m["le"]
        if m["range"] == "exact":
            end, approx = le, False
        else:
            end, approx = min(len(ln), ls + (APPROX_WINDOW if m["range"] == "end unknown" else 0)), m["range"] == "end unknown"
        total = max(0, end - ls + 1)
        if m["kind"] in ("class", "struct", "interface") and total > max_lines:
            members = [{"k": self.idx.keys[i], "ls": self.idx.props[i].get("line_start")} for i in self.idx.sym_by_file.get(f, ())
                       if self.idx.keys[i].split("::", 1)[1].startswith(self.qual_of(m) + ".") and self.idx.props[i].get("line_start")]
            return {"too_long": total, "members": sorted(members, key=lambda x: x["ls"])[:30]}
        shown = min(total, max_lines)
        body = [f"{n:>5}  {ln[n - 1]}" for n in range(ls, ls + shown) if n <= len(ln)]
        return {"lines": body, "more": max(0, total - shown), "approx": approx}

    def qual_of(self, m) -> str:
        return m["k"].split("::", 1)[1]

    # ── outline ───────────────────────────────────────────────────────────
    def skipped_files(self) -> dict[str, str]:
        """Files the symbol build could not read, path -> reason (symbols-manifest.json, #109)."""
        if self._skipped is None:
            self._skipped = {}
            store = getattr(self.api, "store", None)
            if store is not None:
                try:
                    self._skipped = json.loads((store / "symbols-manifest.json").read_text()).get("skipped_files") or {}
                except (OSError, ValueError, AttributeError):
                    pass
        return self._skipped

    def _skipped_reply(self, path: str) -> dict | None:
        rel = repo_path(path)
        skipped = self.skipped_files()
        hits = [f for f in skipped if f == rel or f.endswith("/" + rel)]
        if len(hits) != 1:
            return None
        return {"path": hits[0], "skipped": skipped[hits[0]], "_meta": {}}

    def outline(self, path: str, limit: int = 200, offset: int = 0) -> dict:
        f, cands = self.resolve_file(path)
        if f is None and (sk := self._skipped_reply(path)):
            return sk
        if f is None:
            d = path.strip().strip("/")
            under = [(g, ids) for g, ids in self.idx.sym_by_file.items() if g.startswith(d + "/")]
            if under:
                rows = sorted(((g, len(ids)) for g, ids in under), key=lambda x: (-x[1], x[0]))
                return {"path": d, "directory": True, "files": [{"f": g, "n": n} for g, n in rows[:40]], "n_files": len(rows), "n": sum(n for _, n in rows)}
            return {"path": path, "error": "no tracked file with symbols by that path", "candidates": cands}
        ids = sorted(self.idx.sym_by_file.get(f, ()), key=lambda i: (self.idx.props[i].get("line_start") or 0, -(self.idx.props[i].get("line_end") or 0)))
        quals = [self.qual[i] for i in ids]
        rows = []
        for i, q in zip(ids, quals):
            parents = [p for p in quals if q.startswith(p + ".")]
            p = self.idx.props[i]; ls, le = p.get("line_start"), p.get("line_end")
            rows.append({"name": q.rsplit(".", 1)[-1], "q": q, "kind": p.get("kind"), "ls": ls, "le": le, "range": range_state(f, ls, le),
                         "depth": len(parents), "doc": (p.get("docstring_summary") or "")[:80]})
        suffix = "." + f.rsplit(".", 1)[-1] if "." in f else ""
        imports = []
        if suffix in IMPORT_RE:
            rx = re.compile(IMPORT_RE[suffix])
            for n, text in enumerate(self.lines(f)[:400], 1):
                if rx.match(text):
                    imports.append(f"{n}: {text.strip()[:110]}")
                if len(imports) >= 25:
                    break
        offset = max(0, int(offset or 0))  # symbols to skip: the next page of a file too large for one reply (#91)
        out = {"path": f, "n": len(rows), "symbols": rows[offset:offset + limit], "imports": [] if offset else imports,
               "lines": len(self.lines(f)), "offset": offset}
        if len(rows) > offset + limit:
            out["omitted"] = len(rows) - offset - limit
        if not rows and (sk := self._skipped_reply(f)):
            return sk
        if not rows:
            out["note"] = "no symbols indexed for this file (a language devkb does not read, or a file with no definitions)"
        return out

    # ── uses ──────────────────────────────────────────────────────────────
    def _prose(self, f: str) -> tuple[set[int], dict[int, int]]:
        """A Python file's docstring lines and, per line, the column its comment starts at: where a word match is prose."""
        doc: set[int] = set(); comment: dict[int, int] = {}
        if not f.endswith(".py"):
            return doc, comment
        try:
            first = True
            for t in tokenize.generate_tokens(io.StringIO("\n".join(self.lines(f)) + "\n").readline):
                if t.type == tokenize.COMMENT:
                    comment[t.start[0]] = t.start[1]
                elif t.type == tokenize.STRING and first:  # a string standing alone as a statement: a docstring
                    doc.update(range(t.start[0], t.end[0] + 1))
                if t.type not in (tokenize.COMMENT, tokenize.NL):
                    first = t.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
        except (tokenize.TokenError, SyntaxError, IndentationError):
            pass
        return doc, comment

    def _hit_rank(self, f: str, ln: int, text: str, name: str, mode: str, prose) -> int:
        """0 a call, 1 other code, 2 a comment or docstring: the per-file cap keeps code before prose (#89)."""
        doc, comment = prose
        line = text
        if f.endswith(".py"):
            if ln in doc:
                return 2
            raw = self.lines(f)[ln - 1] if 0 < ln <= len(self.lines(f)) else text
            line = raw[:comment[ln]] if ln in comment else raw
        else:
            stripped = text.lstrip()
            if stripped.startswith(("//", "/*", "*", "#", "<!--")):
                return 2
            line = text.split("//", 1)[0]
        if mode != "word":  # plain text: code or prose only
            return 1 if name in line else 2
        word = re.escape(name.rsplit(".", 1)[-1])
        if not re.search(rf"\b{word}\b", line):
            return 2
        if f.endswith(CXX_SUFFIX):
            m = re.search(rf"\b{word}\s*(?:<[^;(){{}}]*>\s*)?\(", line)   # `f<T>(x)` is a call too
            if not m:
                return 1
            before = line[:m.start()].strip()
            if before.endswith(("::", ".", "->")) or not before:
                return 0
            # a type before the name, with no operator or call keyword in between: a declaration, not a call (#114)
            if re.fullmatch(r"[\w:<>,*&\s]+", before) and not re.search(
                    r"\b(return|new|throw|else|case|delete|co_return|co_yield|co_await|sizeof|typeof|not|and|or)\s*$", before):
                return 1
            return 0
        return 0 if re.search(rf"(?<!def )(?<!class )(?<!function )(?<!func )\b{word}\s*\(", line) else 1  # a definition is code, not a call

    def _def_spans(self, i: int) -> list[tuple[int, int]]:
        """Each definition's own line range; a C/C++ node merges overloads and specialisations but records every span."""
        p = self.idx.props[i]
        own = [(int(a), int(b)) for a, b in (p.get("overload_spans") or ()) if a]
        if own:
            return own
        return [(p["line_start"], p.get("line_end") or p["line_start"])]

    def _enclosing(self, f: str):
        spans = []
        for i in self.idx.sym_by_file.get(f, ()):
            p = self.idx.props[i]
            if p.get("line_start"):
                for a, b in self._def_spans(i):
                    spans.append((a, b, self.qual[i], p.get("kind")))
        spans.sort()
        return spans

    def uses(self, name: str, under: str = "", docs: bool = False, files: int = 12, hits: int = 36, per_file: int = 3) -> dict:
        q = name.strip()
        if not q:
            return {"error": "give a name or a pattern"}
        regexy = q.lower().startswith("re:") or bool(REGEXY.search(q))
        if regexy:
            pat = q[3:] if q.lower().startswith("re:") else q
            args = ["-E", "-e", pat]
            mode = "regex"
        elif re.fullmatch(r"[A-Za-z_][\w.$]*", q):
            args = ["-w", "-F", "-e", q]
            mode = "word"
        else:
            args = ["-F", "-e", q]
            mode = "text"
        under = repo_path(under).rstrip("/") if under else ""
        if under and (self.root / under).is_file():  # a file path narrows to that file, not to a directory under it (#90)
            spec = [":(literal)" + under]
        else:
            spec = [":(glob)" + under + "/**"] if under else []
        excl = [] if docs else [f":(exclude,glob)**/*{s}" for s in NOT_CODE]
        cmd = ["git", "grep", "-n", "-I", "--no-color", "--max-count=60", *args, "--", *(spec or ["."]), *excl]
        try:
            proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=25)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"error": f"search failed: {e}"}
        if proc.returncode not in (0, 1):
            return {"error": (proc.stderr or "git grep failed").strip()[:200]}
        by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
        total = 0
        for line in proc.stdout.splitlines()[:6000]:
            m = re.match(r"([^:]+):(\d+):(.*)", line)
            if m:
                by_file[m.group(1)].append((int(m.group(2)), m.group(3))); total += 1
        defs = []
        if mode == "word":
            r = self.resolve(q, limit=4)
            if r.get("how") in ("exact", "suffix") and r["matches"]:
                for m in r["matches"]:
                    sp = self._def_spans(m["i"])
                    if len(sp) < 2:
                        sp = [(m["ls"], m["le"])]
                    f0 = m["k"].split("::", 1)[0]
                    for a, b in sp:
                        defs.append({"k": m["k"], "kind": m["kind"], "ls": a, "le": b, "range": range_state(f0, a, b) if len(sp) > 1 else m["range"]})
        ranked = sorted(by_file.items(), key=lambda kv: (self.api._is_test(kv[0]), -len(kv[1]), kv[0]))
        out_files = []; shown = 0
        for f, hs in ranked[:files]:
            spans = self._enclosing(f); rows = []
            keep = hs[:per_file]
            if mode != "regex" and len(hs) > per_file:  # code before comments and docstrings within the cap (#89)
                prose = self._prose(f)
                ranked_hs = sorted(hs, key=lambda h: (self._hit_rank(f, h[0], h[1], q, mode, prose), h[0]))[:per_file]
                keep = ranked_hs if f.endswith(CXX_SUFFIX) else sorted(ranked_hs)   # C/C++: calls first, then declarations (#114)
            for ln, text in keep:
                if shown >= hits:
                    break
                best = None
                for s0, e0, qn, _kind in spans:
                    if s0 <= ln <= e0 and (e0 > s0 or ln == s0) and (best is None or e0 - s0 < best[0]):
                        best = (e0 - s0, qn)
                if best:
                    inner = (best[1], False)
                else:                                   # a symbol with no known end: the nearest one above the hit
                    prev = [] if f.endswith(CXX_SUFFIX) else [x for x in spans if x[0] <= ln]   # C/C++ spans are exact: outside them is top level
                    inner = (prev[-1][2], True) if prev else None
                rows.append({"line": ln, "text": text.strip()[:110], "in": inner[0] if inner else None, "approx": bool(inner and inner[1])})
                shown += 1
            out_files.append({"f": f, "n": len(hs), "test": self.api._is_test(f), "hits": rows})
        keyed = self.key_uses(q, under) if mode == "word" else []
        return {"name": q, "mode": mode, "definitions": defs, "key_uses": keyed, "n_hits": total, "n_files": len(by_file), "files": out_files,
                "omitted_files": max(0, len(ranked) - files), "capped": total >= 6000,
                "note": "text matches, not resolved references: a match inside a string or comment is still listed"}

    # ── search_docs ───────────────────────────────────────────────────────
    def search_docs(self, query: str, under: str = "", files: int = 8, per_file: int = 3) -> dict:
        q = query.strip()
        if not q:
            return {"error": "give words or a pattern"}
        if q.lower().startswith("re:") or REGEXY.search(q):
            args = ["-i", "-E", "-e", q[3:] if q.lower().startswith("re:") else q]; mode = "regex"; ws = []
        else:
            ws = [w for w in re.split(r"\s+", q) if w]
            args = ["-i", "-F", "--all-match"]
            for w in ws:
                args += ["-e", w]
            mode = "words"
        spec = [f":(glob){under.rstrip('/') + '/' if under else ''}**/*{s}" for s in DOC_SUFFIX] + ([f":(glob){under.rstrip('/') + '/' if under else ''}*{s}" for s in DOC_SUFFIX])
        try:
            proc = subprocess.run(["git", "grep", "-n", "-I", "--no-color", "--max-count=30", *args, "--", *spec], cwd=self.root,
                                  capture_output=True, text=True, timeout=25)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"error": f"search failed: {e}"}
        if proc.returncode not in (0, 1):                # 1 is "no match"; anything else, e.g. a rejected regex, is not (#55)
            return {"query": q, "error": f'search_docs could not search for "{q}": '
                                         f'{(proc.stderr or "git grep failed").strip()[:200]}'}
        by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for line in proc.stdout.splitlines()[:4000]:
            m = re.match(r"([^:]+):(\d+):(.*)", line)
            if m:
                by_file[m.group(1)].append((int(m.group(2)), m.group(3)))
        def weight(f):
            return (0 if re.search(r"(^|/)(spec|specs|adr|decisions?)/", f) else 1 if re.search(r"(^|/)docs?/", f) else 2, -len(by_file[f]), f)
        out = []
        for f in sorted(by_file, key=weight)[:files]:
            ln = self.lines(f); rows = []
            for n, text in by_file[f][:per_file]:
                head = next((ln[k].lstrip("# ").strip() for k in range(min(n, len(ln)) - 1, -1, -1) if re.match(r"^#{1,6}\s+\S", ln[k])), None)
                rows.append({"line": n, "text": text.strip()[:140], "under": head[:70] if head else None})
            out.append({"f": f, "n": len(by_file[f]), "hits": rows})
        return {"query": q, "mode": mode, "n_files": len(by_file), "files": out, "omitted_files": max(0, len(by_file) - files)}


# ── text rendering: what an agent reads (ADR-DEVKB-010 §2) ──────────────
def _stale(reply: dict) -> str:
    meta = reply.get("_meta") or {}
    if not meta.get("stale"):
        return ""
    ahead = f", repository is {meta['behind']} commits ahead" if meta.get("behind") else ""
    return f"\ngraph stale: built at {meta.get('head', '?')}{ahead}; ranges and names may have moved, re-read what you edit."


def fit_text(text: str, budget: int = BUDGET) -> str:
    """Whole lines are cut from the end until the reply fits, and the cut is counted."""
    if len(text.encode()) <= budget:
        return text
    lines = text.splitlines(); cut = 0
    while lines and len("\n".join(lines).encode()) > budget - 90:
        lines.pop(); cut += 1
    return "\n".join(lines) + f"\n(output cut at {budget} bytes: {cut} more lines; ask for fewer lines or narrow with under=PATH)"


def _span(m: dict) -> str:
    return f"L{m['ls']}-{m['le']}" if m["range"] == "exact" else f"L{m['ls']} (end unknown)" if m["range"] == "end unknown" else f"L{m['ls']}"


def _render_keys(rows: list[dict]) -> str:
    out = []
    for x in rows[:30]:
        parts = [f"{m} L{','.join(map(str, x[m]))}" for m in ("writes", "reads") if x[m]]
        out.append(f"{x['f']}  {x['in'] or 'module level'}  " + "; ".join(parts))
    if len(rows) > 30:
        out.append(f"({len(rows) - 30} more functions)")
    return "\n".join(out)


def render_symbol(r: dict) -> str:
    if r.get("batch"):
        share = BUDGET // len(r["batch"])
        return "\n\n".join(fit_text(render_symbol(x), share) for x in r["batch"])
    if r.get("error"):
        return r["error"]
    if not r["matches"] and r.get("key_uses"):
        return fit_text(f'no symbol named "{r["query"]}"; it is used as a string key:\n' + _render_keys(r["key_uses"]))
    if not r["matches"]:
        out = [f'no symbol named "{r["query"]}"']
        if r.get("suggestions"):
            out.append("closest names (not matches): " + "; ".join(f"{x['name']} ({x['path']}, {x['score']})" for x in r["suggestions"]))
        return fit_text("\n".join(out)) + _stale(r)
    shown = len(r["matches"])
    out = [f'symbol "{r["query"]}": {r["n"]} match{"es" if r["n"] != 1 else ""} ({r["how"]})' + (f", showing {shown}" if r["n"] > shown else "")]
    for n, m in enumerate(r["matches"], 1):
        f, q = m["k"].split("::", 1)
        out.append(f"{n}. {f}  {m['kind']}  {_span(m)}  {m.get('sig', '')}")
        also = (" (+ itself)" if m.get("self_call") else "") + \
            (f" (+ named without a call at {m['value_refs']} site(s))" if m.get("value_refs") else "")  # #70, #69
        if m.get("unresolved"):  # the count is a lower bound, as the packs' Coverage says (#87)
            shared = f"; {m['shared_by']} symbols share the name" if (m.get("shared_by") or 0) > 1 else ""
            also = f"+{also} (calls under this name from {m['unresolved']} more function(s) not attributed{shared})"
        tail = (f'"{m["doc"]}"   ' if m.get("doc") else "") + (f"callers {m['callers']}{also}   " if m["callers"] or also else "") \
            + (f"references {m['refs']}   " if m.get("refs") else "") \
            + f"how {m['how']}"
        out.append(f"   {q}   {tail}")
        if m.get("moved") is not None:
            out.append(f"   adjusted: the graph recorded this elsewhere; found {m['moved']:+d} line(s) away" if isinstance(m["moved"], int) else f"   moved: {m['moved']}")
        src = m.get("source")
        if src and src.get("lines") is not None:
            out += ["   ---"] + ["   " + x for x in src["lines"]]
            if src["more"]:
                out.append(f"   ({src['more']} more lines; {_span(m)})")
            if src["approx"]:
                out.append("   approximate window, not the symbol's range (its end is unknown for this language)")
            if src.get("capped"):
                out.append(f"   (lines capped at {src['capped']})")
        elif src and src.get("too_long"):
            out.append(f"   {src['too_long']} lines: too long to print; members: " + ", ".join(f"{x['k'].split('::', 1)[1].rsplit('.', 1)[-1]} L{x['ls']}" for x in src["members"][:20]))
    if r["n"] > shown:
        out.append(f"({r['n'] - shown} more matches; narrow with kind= or under=)")
    return fit_text("\n".join(out)) + _stale(r)


def render_outline(r: dict) -> str:
    if r.get("error"):
        return r["error"] + ("; did you mean: " + ", ".join(r["candidates"]) if r.get("candidates") else "")
    if r.get("skipped"):
        return f"{r['path']}: not indexed, the build could not read it ({r['skipped']}); read the file itself"
    if r.get("directory"):
        return fit_text(f"{r['path']}/  {r['n']} symbols in {r['n_files']} files\n" + "\n".join(f"  {x['f']}  {x['n']} symbols" for x in r["files"])) + _stale(r)
    suffix = "." + r["path"].rsplit(".", 1)[-1] if "." in r["path"] else ""
    rng = "start-only" if suffix in START_ONLY else "exact"
    offset = r.get("offset") or 0
    out = [f"{r['path']}  {LANG.get(suffix, 'unknown language')} {r['n']} symbols  range={rng}  ({r['lines']} lines)"
           + (f"  from symbol {offset + 1}" if offset else "")]
    out += [f"  {i}" for i in r["imports"][:30]]
    rows = []
    for s in r["symbols"]:
        span = f"L{s['ls']}-{s['le']}" if s["range"] == "exact" else f"L{s['ls']}"
        rows.append("  " * (s["depth"] + 1) + f"{s['kind']} {s['name']}  {span}" + (f'  "{s["doc"]}"' if s["doc"] else ""))
    # Cut whole symbols, not lines, and name where the next page starts, so every member can be listed (#91).
    size = len("\n".join(out).encode())
    room = BUDGET - 200
    shown = 0
    for line in rows:
        size += len(line.encode()) + 1
        if size > room:
            break
        shown += 1
    out += rows[:shown]
    rest = r["n"] - offset - shown
    if rest > 0:
        nxt = offset + shown
        why = f"output cut at {BUDGET} bytes" if shown < len(rows) else "symbol limit reached"
        out.append(f"({why}: symbols {offset + 1}-{nxt} of {r['n']} shown, {rest} more; "
                   f"the rest: outline with offset={nxt} (shell: --offset {nxt}))")
    if r.get("note"):
        out.append(f"no indexed symbols in {r['path']}; indexed languages: Python, TypeScript, JavaScript, C#, C, C++, Odoo XML")
    return fit_text("\n".join(out)) + _stale(r)


def render_uses(r: dict) -> str:
    if r.get("error"):
        return r["error"]
    out = [f'uses "{r["name"]}": text matches, not resolved references; tracked files only, not complete   mode {r["mode"]}']
    for d in r["definitions"][:5]:
        out.append(f"defined: {d['k'].split('::', 1)[0]} {_span(d)} {d['kind']}")
    if r.get("key_uses"):
        out.append("as a string key (written / read, by function):")
        out.append(_render_keys(r["key_uses"]))
    shown = tests_cut = 0
    for f in r["files"]:
        for h in f["hits"]:
            where = f"in {h['in']}" if h["in"] and not h["approx"] else f"after {h['in']}" if h["in"] else "top level"
            out.append(f"{f['f']}:{h['line']}  {where}  {h['text']}")
            shown += 1
        tests_cut += (f["n"] - len(f["hits"])) if f["test"] else 0
    omitted_hits = r["n_hits"] - shown
    if omitted_hits > 0 or r["omitted_files"]:
        out.append(f"showing {shown} of {r['n_hits']}{'+' if r.get('capped') else ''} hits in {len(r['files'])} of {r['n_files']} files; omitted: {omitted_hits} hits"
                   + (f" ({tests_cut} in tests)" if tests_cut else "") + f", {r['omitted_files']} files. Narrow with under=PATH.")
    return fit_text("\n".join(out)) + _stale(r)


def render_docs(r: dict) -> str:
    if r.get("error"):
        return r["error"]
    if not r["files"]:
        return f'no documentation file matches "{r["query"]}" ({r["mode"]}).' + _stale(r)
    out = [f'search_docs "{r["query"]}": {r["n_files"]} documents ({r["mode"]})']
    for f in r["files"]:
        out.append(f"{f['f']}  {f['n']} matching lines")
        for h in f["hits"]:
            out.append(f"  L{h['line']}  under \"{h['under'] or 'top of file'}\"  {h['text']}")
    if r["omitted_files"]:
        out.append(f"({r['omitted_files']} more documents)")
    return fit_text("\n".join(out)) + _stale(r)


RENDER = {"symbol": render_symbol, "outline": render_outline, "uses": render_uses, "search_docs": render_docs}


def main(argv: list[str] | None = None) -> int:
    """`devkb symbol|outline|uses|docs ...`: the same answers as the MCP tools, for a shell."""
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="devkb", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["symbol", "outline", "uses", "docs"])
    ap.add_argument("query")
    ap.add_argument("--project", default=".")
    ap.add_argument("--source", action="store_true", help="symbol: print the source of the best match")
    ap.add_argument("--kind", default="")
    ap.add_argument("--under", default="")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--lines", type=int, default=MAX_SOURCE, help="symbol --source: lines to print (default 80, at most 200)")
    ap.add_argument("--docs", action="store_true", help="uses: include documentation files")
    ap.add_argument("--offset", type=int, default=0, help="outline: skip this many symbols (the next page of a large file)")
    a = ap.parse_args(argv)
    from devkb.process_api import ProcessAPI  # noqa: PLC0415
    api = ProcessAPI(a.project, telemetry_source="cli")
    tool = {"symbol": "symbol", "outline": "outline", "uses": "uses", "docs": "search_docs"}[a.cmd]
    kw = {"symbol": dict(query=a.query, source=a.source, kind=a.kind, under=a.under, limit=a.limit, lines=a.lines),
          "outline": dict(path=a.query, offset=a.offset), "uses": dict(name=a.query, under=a.under, docs=a.docs),
          "search_docs": dict(query=a.query, under=a.under)}[tool]
    print(RENDER[tool](api.call(tool, **kw)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
