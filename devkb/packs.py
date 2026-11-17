#!/usr/bin/env python3
"""Predefined graph packs: the answer to a chain-or-join question, written before the session starts (ODSF-313).

The workflow benchmark (docs/workflow-benchmark-odsf310.md) showed where a graph pays: walking call chains and joining
code to tests. It also showed why it often does not: every graph turn pays for tool definitions and a reply, and the
agent re-reads the code to check the answer anyway. A pack removes both. It is generated from what a ticket or task
already names (an error message, a function, a role), goes into the prompt, so no MCP server or tool definitions are
loaded, and it carries what makes checking unnecessary:

  evidence   every caller, handler and test given as `path:line` with the line of code that makes the call
  coverage   either every call site under the name was attributed, or the files holding the ones that were not
  freshness  the commit the graph was built at, and which of the listed files changed since in the working tree
  shape      sections in the order the deliverable needs them

  python3 devkb/packs.py --project OCO error "workflow needs a non-empty 'states' object"
  python3 devkb/packs.py --project OCO change revoke_user_sessions
  python3 devkb/packs.py --project OCO refactor add_edge --role BE
  python3 devkb/packs.py --project OCO ticket GH-123      a ticket's pull requests, commits, changed functions, tests
  python3 devkb/packs.py --project OCO pr 456             a pull request's commits, changed functions, tests, issues closed
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.cpp_symbols import C_LIMITS_TEXT, CXX_LIMITS_TEXT, is_cxx_path  # noqa: E402
from devkb.process_api import ProcessAPI, is_test_path  # noqa: E402
from devkb.service import GraphNotBuilt  # noqa: E402

MAX_DEPTH = 6


_KIND_TEXT = {"c-abi": "C ABI", "jni": "JNI", "pyinit": "Python module init", "pyc-method": "CPython method table",
              "pybind11": "pybind11"}
_REASON_TEXT = {
    "dynamic-dispatch": "a virtual or overriding method may be reached through a base-class pointer",
    "implicit-call": "constructors, destructors and operators are invoked without a call in the text",
    "unread-file": "a C/C++ file was too large or unreadable and was not read",
    "indirect-reference": "the function's name is used without a call (a function-pointer table, an ops struct, a callback), so who calls it is not visible",
    "dynamic-import": "a name is looked up at run time (`dlsym`, `getattr` on a library handle), so the callee is not known",
    "ambiguous-abi-name": "two definitions bear the same name on the wire, so a call from another language cannot be attributed",
    "lambda-binding": "a pybind11 binding to a lambda has no function in the source to link to",
}


class Packer:
    def __init__(self, api: ProcessAPI) -> None:
        self.api, self.idx = api, api.idx
        self._lines: dict[str, list[str]] = {}

    # ── evidence ──────────────────────────────────────────────────────────────
    def _file(self, rel: str) -> list[str]:
        if rel not in self._lines:
            try:
                self._lines[rel] = (self.api.root / rel).read_text(errors="replace").splitlines()
            except OSError:
                self._lines[rel] = []
        return self._lines[rel]

    def call_site(self, caller: int, name: str) -> str:
        """`path:line: code` for the first line in `caller`'s body that calls `name`, or the caller's own line."""
        key = self.api._key(caller)
        rel = key.split("::")[0]
        p = self.idx.props[caller]
        start, end = int(p.get("line_start") or 1), int(p.get("line_end") or p.get("line_start") or 1)
        lines = self._file(rel)
        rx = re.compile(r"\b" + re.escape(name) + r"\s*\(")
        for n in range(start, min(end, len(lines)) + 1):
            if rx.search(lines[n - 1]):
                return f"{rel}:{n}: {lines[n - 1].strip()[:140]}"
        return f"{rel}:{start}: (def {key.split('::')[-1]})"

    def def_line(self, sym: int) -> str:
        key = self.api._key(sym)
        rel, start = key.split("::")[0], int(self.idx.props[sym].get("line_start") or 1)
        lines = self._file(rel)
        return f"{rel}:{start}: {lines[start - 1].strip()[:140] if 0 < start <= len(lines) else ''}"

    def _via(self, caller: int, callee: int) -> str:
        """` (via ctypes)` when the call crosses a language: the mechanism that linked it (ADR-DEVKB-009)."""
        m = self.idx.boundary.get((caller, callee))
        return f" (via {m})" if m else ""

    def _name(self, sym: int) -> str:
        return self.api._key(sym).split("::")[-1].split(".")[-1]

    def freshness(self, files: list[str]) -> str:
        head = self.idx.git_head
        try:
            changed = set(subprocess.run(["git", "diff", "--name-only", head], cwd=self.api.root, capture_output=True,
                                         text=True, timeout=10).stdout.split())
        except (OSError, subprocess.SubprocessError):
            changed = set()
        hit = sorted(set(files) & changed)
        return (f"Built from the dev-process graph at commit `{head[:10]}`. "
                + (f"**Changed since, re-read these:** {', '.join(f'`{f}`' for f in hit)}." if hit
                   else "None of the files below has changed since; the line numbers are current."))

    def coverage(self, syms: list[int], shown: set[str]) -> str:
        """The coverage statement; for a C/C++ symbol, the limit statement follows it, Complete or not (ADR-DEVKB-008 §4)."""
        text = self._coverage_text(syms, shown)
        if any(is_cxx_path(self.api._key(x).split("::")[0]) for x in syms):
            c = self.api._coverage(syms, shown)
            if c.get("unattributed_errors"):
                text += (f" {c['unattributed_errors']} `throw` or `assert` site(s) in these functions carry a message that is "
                         "not a literal, so their text is not searchable.")
            profile = c.get("profile")
            text += "\n\n" + (C_LIMITS_TEXT if profile == "c" else CXX_LIMITS_TEXT if profile == "cpp" else C_LIMITS_TEXT + " " + CXX_LIMITS_TEXT)
        return text

    def _coverage_text(self, syms: list[int], shown: set[str]) -> str:
        c = self.api._coverage(syms, shown)
        cxx = any(is_cxx_path(self.api._key(x).split("::")[0]) for x in syms)
        text = self._coverage_core(c, syms, shown, cxx)
        if c.get("qualified"):
            kinds = c["boundary_kind"] if isinstance(c["boundary_kind"], list) else [c["boundary_kind"]]
            note = f"Callers may exist in languages not read ({', '.join(_KIND_TEXT.get(k, k) for k in kinds)})."
            if c.get("dynamic_lookups"):
                note += (f" {c['dynamic_lookups']} dynamic lookup(s) in this repository (`dlsym`, `getattr` on a library handle) "
                         "are not followed, so a caller may hide behind one.")
            if c.get("complete"):
                return f"**Complete for the languages read** ({', '.join(c['languages_read'])}). {note}"
            return f"{text} {note}"
        return text

    def _coverage_core(self, c: dict, syms: list[int], shown: set[str], cxx: bool) -> str:
        if c.get("complete"):
            if cxx:
                return ("**Complete.** Every call site of these names visible in the source text was attributed to a target; "
                        "this does not rule out a caller at run time.")
            return "**Complete.** Every call site under these names was attributed to its target; nothing else calls them."
        if c.get("reasons") and not c.get("unresolved_calls"):
            return ("**Incomplete: the graph cannot follow every call to these names** ("
                    + ", ".join(f"`{r}`: {_REASON_TEXT[r]}" for r in c["reasons"]) + ").")
        names = {self.api._key(x).split("::")[-1].split(".")[-1] for x in syms}
        name = next(iter(names)) if len(names) == 1 else ""
        listed = c.get("search_files", [])
        total = max(c.get("search_file_count") or 0, len(listed))
        files = ", ".join(f"`{f}`" for f in listed) or "(files not recorded)"
        shared = f" {c['shared_by']} symbols share the name, so most may be calls to the others." if c.get("shared_by") else ""
        head = f"**Incomplete: {c['unresolved_calls']} call site(s) under this name could not be attributed.**{shared} "
        if c.get("reasons"):
            head += "Also: " + ", ".join(f"`{r}` ({_REASON_TEXT[r]})" for r in c["reasons"]) + ". "
        if c.get("in_listed_files"):
            return head + "They are in files already listed above; check those files' other calls under this name."
        if total <= len(listed):
            return head + f"Search only these files for them: {files}."
        return head + (f"They are in {total} files; the {len(listed)} with the most: {files}. Search the whole "
                       f"repository for the rest" + (f" (`grep -rn '{name}(' --include='*.py' .`)" if name else "") + ".")

    # ── walking ───────────────────────────────────────────────────────────────
    def up(self, start: set[int]) -> dict[int, int]:
        """Every production function that reaches `start` through calls: {caller: the callee it calls on the way}."""
        parent: dict[int, int] = {}
        frontier = set(start)
        for _ in range(MAX_DEPTH):
            nxt = set()
            for s in frontier:
                for c in set(self.idx.sources("CALLS", s)) | set(self.idx.sources("CALLS_API", s)):
                    if c in parent or c in start or is_test_path(self.api._key(c).split("::")[0]):
                        continue
                    parent[c] = s
                    nxt.add(c)
            frontier = nxt
            if not frontier:
                break
        return parent

    def _reachers(self, parent: dict[int, int], cap: int = 40) -> list[str]:
        """Every production function that reaches the subject through calls, each with the call that proves it. A
        repository without route handlers (a command-line tool, a library) has no other answer to "what reaches it"."""
        keys = sorted(parent, key=self.api._key)
        out = ["", f"## Functions that reach it, at any depth ({len(keys)})"]
        out += [f"- `{self.api._key(c)}` — `{self.call_site(c, self._name(parent[c]))}`" for c in keys[:cap]]
        if len(keys) > cap:
            out.append(f"- … {len(keys) - cap} more")
        return out if keys else out + ["- none the graph resolves"]

    def handlers(self, parent: dict[int, int], start: set[int]) -> list[tuple[int, list[int]]]:
        out = []
        for c in sorted(set(parent) | start, key=self.api._key):
            if self.idx.ep_by_owner.get(self.api._key(c)):
                path, x = [c], c
                while x in parent:
                    x = parent[x]
                    path.append(x)
                out.append((c, path))
        return out

    def tests(self, syms: set[int]) -> dict[str, list[tuple[int, int]]]:
        """Test files with (test function, the symbol it calls) for every test that calls any of `syms`."""
        out: dict[str, list[tuple[int, int]]] = {}
        for s in syms:
            for c in set(self.idx.sources("CALLS", s)):
                rel = self.api._key(c).split("::")[0]
                if is_test_path(rel):
                    out.setdefault(rel, []).append((c, s))
        return out

    def _tests_section(self, tests: dict[str, list[tuple[int, int]]]) -> list[str]:
        lines = []
        for rel in sorted(tests):
            c, s = tests[rel][0]
            more = f" (+{len(tests[rel]) - 1} more tests)" if len(tests[rel]) > 1 else ""
            lines.append(f"- `{rel}`{more} — `{self.call_site(c, self._name(s))}`")
        return lines or ["- none in the graph"]

    def _run(self, files: list[str]) -> str:
        return self.api._run_line(sorted(files)) if files else ""

    # ── the three packs ───────────────────────────────────────────────────────
    def error(self, message: str) -> str:
        r = self.api.rca_trace(message)
        if "error" in r:
            return f"# Graph pack: error\n\nThe graph has no error matching \"{message}\". Search the code."
        raisers = [self.api._resolve(k)[0] for k in r["raisers"]]
        raisers = [x for x in raisers if x is not None]
        parent = self.up(set(raisers))
        hs = self.handlers(parent, set(raisers))
        closure = set(parent) | set(raisers)
        tests = self.tests(closure)
        out = [f"# Graph pack: error \"{message[:80]}\"", "", self.freshness(sorted({self.api._key(x).split('::')[0] for x in closure})), "",
               "## Raised by"]
        out += [f"- `{self.api._key(x)}` — `{self.def_line(x)}`" for x in raisers]
        out += self._reachers(parent)
        if self.idx.ep_by_owner:
            out += ["", f"## Route handlers that reach it ({len(hs)})"]
        for h, path in hs:
            chain = " → ".join(f"`{self.api._key(p).split('::')[-1]}`" for p in path)
            out.append(f"- `{self.api._key(h)}` ({', '.join(self.api._key(e) for e in self.idx.ep_by_owner[self.api._key(h)][:2])})")
            for a, b in zip(path, path[1:]):
                out.append(f"  - `{self.call_site(a, self._name(b))}`")
            out.append(f"  - path: {chain}")
        if not hs and self.idx.ep_by_owner:
            out.append("- none: no route handler reaches it through calls the graph resolves")
        out += ["", f"## Test files on those paths ({len(tests)})"] + self._tests_section(tests)
        if tests:
            out += ["", f"Run: `{self._run(list(tests))}`"]
        out += ["", "## Coverage", self.coverage(sorted(closure, key=self.api._key)[:40], set(tests) | {self.api._key(x).split('::')[0] for x in closure})]
        return "\n".join(out + ["", HOW_TO_USE])

    def change(self, name: str, path: str = "") -> str:
        i, err = self.api._resolve(f"{path}::{name}" if path and "::" not in name else name)
        if i is None and path:
            cands = [s for s in self.api._by_name(name) if self.api._key(s).startswith(path + "::")]
            i = cands[0] if len(cands) == 1 else None
        if i is None:
            return f"# Graph pack: change\n\nThe graph cannot resolve `{name}`" + (f" in `{path}`" if path else "") + ". Search the code."
        parent = self.up({i})
        hs = self.handlers(parent, {i})
        closure = set(parent) | {i}
        tests = self.tests(closure)
        out = [f"# Graph pack: changing `{self.api._key(i)}`", "",
               self.freshness(sorted({self.api._key(x).split('::')[0] for x in closure})), "", f"Defined at `{self.def_line(i)}`."]
        out += self._reachers(parent)
        if self.idx.ep_by_owner:
            out += ["", f"## Route handlers that reach it ({len(hs)})"]
        for h, path_ in hs:
            out.append(f"- `{self.api._key(h)}` ({', '.join(self.api._key(e) for e in self.idx.ep_by_owner[self.api._key(h)][:2])}) — path: "
                       + " → ".join(f"`{self.api._key(p).split('::')[-1]}`" for p in path_))
            for a, b in zip(path_, path_[1:]):
                out.append(f"  - `{self.call_site(a, self._name(b))}`")
        if not hs and self.idx.ep_by_owner:
            out.append("- none: no route handler reaches it through calls the graph resolves")
        out += ["", f"## Test files to run ({len(tests)}): every test calling it or a function on those paths"] + self._tests_section(tests)
        if tests:
            out += ["", f"Run: `{self._run(list(tests))}`"]
        out += ["", "## Coverage", self.coverage(sorted(closure, key=self.api._key)[:40], set(tests) | {self.api._key(x).split('::')[0] for x in closure})]
        return "\n".join(out + ["", HOW_TO_USE])

    def file(self, path: str, cap: int = 25) -> str:
        """Before editing a file: which of its functions other files depend on (each with the call that proves it),
        the tests that exercise it, and what the graph could not attribute. A file's contract is what is called from
        outside it, so those functions come first and its private helpers are only counted."""
        path = path.strip().lstrip("./")
        syms = list(self.idx.sym_by_file.get(path, []))
        if not syms:
            return f"# Graph pack: file\n\nThe graph has no code in `{path}`. Search the code."
        rows = []
        for i in syms:
            outside: dict[str, int] = {}
            for c in self.idx.sources("CALLS", i):
                f = self.api._key(c).split("::")[0]
                if f != path:
                    outside.setdefault(f, c)
            rows.append((i, outside))
        used = sorted((r for r in rows if r[1]), key=lambda r: (-len(r[1]), self.api._key(r[0])))
        tests = self.tests(set(syms) | set(self.up(set(syms))))  # tests that reach the file through calls at any depth
        dependants = sorted({f for _, o in used for f in o})
        out = [f"# Graph pack: before editing `{path}`", "", self.freshness([path] + dependants[:40]), "",
               f"## Functions other files call ({len(used)} of {len(syms)})"]
        for i, outside in used[:cap]:
            f, c = next(iter(sorted(outside.items())))
            more = f" and {len(outside) - 1} more file(s)" if len(outside) > 1 else ""
            out.append(f"- `{self.api._key(i).split('::', 1)[1]}` — {len(outside)} file(s): `{self.call_site(c, self._name(i))}`{self._via(c, i)}{more}")
        if len(used) > cap:
            out.append(f"- … {len(used) - cap} more")
        if not used:
            out.append("- none: nothing outside this file calls into it through calls the graph resolves")
        out += ["", f"## Files that depend on it ({len(dependants)})"] + [f"- `{f}`" for f in dependants[:40]]
        out += ["", f"## Tests that exercise it, directly or through callers ({len(tests)})"] + self._tests_section(tests)
        if tests:
            out += ["", f"Run: `{self._run(list(tests))}`"]
        out += self._config_section(path, syms)
        out += ["", "## Coverage", self.coverage(sorted(syms, key=self.api._key)[:40], set(dependants) | set(tests))]
        return "\n".join(out + ["", HOW_TO_USE])

    def _config_section(self, path: str, syms: list[int]) -> list[str]:
        """Kconfig and devicetree options this file reads, each with the file that declares it (ADR-DEVKB-009 §3)."""
        file_i = self.idx.by_key.get(("File", path))
        reads: dict[int, None] = {}
        for src in ([file_i] if file_i is not None else []) + list(syms):
            for k in self.idx.out.get("READS", {}).get(src, []):
                if self.api._key(k).startswith(("kconfig:", "devicetree:")):
                    reads[k] = None
        if not reads:
            return []
        rows = []
        for k in sorted(reads, key=self.api._key):
            decl = sorted(self.api._key(f) for f in self.idx.sources("DECLARES", k))
            rows.append(f"- `{self.api._key(k)}` — " + (f"declared in {', '.join(f'`{d}`' for d in decl[:3])}" if decl
                                                       else "not declared in the repository"))
        return ["", f"## Configuration it reads ({len(rows)})"] + rows[:40] + ([f"- … {len(rows) - 40} more"] if len(rows) > 40 else [])

    def refactor(self, name: str, role: str = "", path: str = "") -> str:
        i, err = self.api._resolve(f"{path}::{name}" if path and "::" not in name else name)
        if i is None:
            cands = [s for s in self.api._by_name(name) if not path or self.api._key(s).startswith(path + "::")]
            i = cands[0] if len(cands) == 1 else None
        if i is None:
            return f"# Graph pack: refactor\n\nThe graph cannot resolve `{name}` unambiguously. Search the code."
        callers = sorted(set(self.idx.sources("CALLS", i)), key=self.api._key)
        by_file: dict[str, list[int]] = {}
        for c in callers:
            by_file.setdefault(self.api._key(c).split("::")[0], []).append(c)
        own = self.api._key(i).split("::")[0]
        # Calls made outside any function (import time, class bodies) have no caller Symbol; the graph keeps their files.
        at_module = sorted(f for f in (self.idx.props[i].get("module_callers") or []) if f != own and f not in by_file)
        dnt = self.api._role_table().get(role, {}).get("dnt", []) if role else []
        files = sorted(set(by_file) | set(at_module))
        blocked = sorted(f for f in files if any(f.startswith(p) for p in dnt))
        tests = sorted(f for f in files if is_test_path(f))
        out = [f"# Graph pack: changing the signature of `{self.api._key(i)}`" + (f" as role {role}" if role else ""), "",
               self.freshness(files), "", f"Defined at `{self.def_line(i)}`.", "",
               f"## Files with a direct caller ({len(files)}, tests included)"]
        for f in files:
            if f not in by_file:
                out.append(f"- `{f}` — called at module level, outside any function")
                continue
            c = by_file[f][0]
            more = f" (+{len(by_file[f]) - 1} more)" if len(by_file[f]) > 1 else ""
            out.append(f"- `{f}`{more} — `{self.call_site(c, self._name(i))}`{self._via(c, i)}")
        out += ["", f"## Test files among them ({len(tests)})"] + ([f"- `{f}`" for f in tests] or ["- none"])
        if role:
            out += ["", f"## Files role {role} must not edit ({len(blocked)})"] + ([f"- `{f}`" for f in blocked] or ["- none"])
        if own not in by_file:
            out += ["", f"(The defining file `{own}` is not counted as a caller.)"]
        out += ["", "## Coverage", self.coverage([i], set(files))]
        return "\n".join(out + ["", HOW_TO_USE])


    # ── ADDENDUM-1 S2: process joins (ODSF-316) ────────────────────────────────
    def _changed_by(self, commits: list[int]) -> dict[int, str]:
        """Module-level production functions, still present, that these commits changed: {symbol: short hash}."""
        changed: dict[int, str] = {}
        for c in commits:
            r = self.api.review_pack(self.api._key(c)[:12])
            for key in r.get("changed_symbols", []):
                path, _, qual = key.partition("::")
                i = self.idx.node("Symbol", key)
                if i is not None and "." not in qual and not is_test_path(path) and self.idx.props[i].get("kind") == "function":
                    changed.setdefault(i, self.idx.props[c].get("short_hash", self.api._key(c)[:10]))
        return changed

    def _pr_commits_to_read(self, prs: list[int]) -> list[int]:
        """Each pull request's commits, minus the ones a merge commit already contains: a merge commit's diff is the
        whole pull request, so reading its second-parent commits too would only repeat it."""
        out: list[int] = []
        for p in prs:
            cs = sorted(set(self.idx.targets("MERGES", p)), key=lambda c: (self.idx.props[c].get("date", ""), self.api._key(c)))
            merge = self.idx.props[p].get("merge_commit")
            m = self.idx.node("Commit", merge) if merge else None
            out += [m] if m is not None and m in cs and self.idx.props[p].get("merge_style") == "merge" else cs
        return out

    def _pr_lines(self, prs: list[int], ticket: int | None = None, cap: int = 15) -> list[str]:
        lines = []
        for p in prs[:cap]:
            props = self.idx.props[p]
            how = ", ".join(x for x in (props.get("state"), props.get("merge_style")) if x)
            mark = ""
            if ticket is not None:
                conf, unverified = self.api._link("CLOSES", p, ticket)
                if conf is not None:
                    mark = f" — closes it at confidence {conf}" + (", **unverified**: the number may be a pull request, not an issue" if unverified else "")
            lines.append(f"- `{self.api._key(p)}` ({how}) {(props.get('title') or '')[:90]}{mark}")
        if len(prs) > cap:
            lines.append(f"- … {len(prs) - cap} more")
        return lines or ["- none in the graph"]

    def _pr_coverage_text(self, unverified: list[str]) -> str:
        cov = self.api.pr_coverage(unverified)
        if cov is None:
            return "the repository has no GitHub remote, so no pull-request links were looked for."
        head = ("**Complete.** The GitHub layer was fetched; the links above are GitHub's own record." if cov["complete"]
                else f"**Incomplete** (GitHub layer: {cov['github']}).")
        note = f" {cov['note']}." if cov.get("note") and not cov["complete"] else ""
        unv = f" Not verified: {', '.join(f'`{u}`' for u in cov['unverified'])}." if cov.get("unverified") else ""
        return head + note + unv

    def ticket(self, ticket_id: str) -> str:
        """A ticket's commits (its own and its pull requests'), the module-level functions they changed that exist now,
        and the tests that call them."""
        t = self.idx.node("Ticket", ticket_id)
        if t is None:
            return f"# Graph pack: ticket {ticket_id}\n\nThe graph has no ticket {ticket_id}. Search the history."
        prs = self.api._ticket_prs(t)
        referencing = set(self.idx.sources("REFERENCES", t))
        via_prs = {c for p in prs for c in self.idx.targets("MERGES", p)}
        commits = sorted(referencing | via_prs, key=lambda c: self.idx.props[c].get("date", ""))
        read = sorted(referencing | set(self._pr_commits_to_read(prs)), key=lambda c: self.idx.props[c].get("date", ""))
        changed = self._changed_by(read)
        tests = self.tests(set(changed))
        out = [f"# Graph pack: ticket {ticket_id} ({(self.idx.props[t].get('title') or '')[:90]})", "",
               self.freshness(sorted({self.api._key(i).split('::')[0] for i in changed})), ""]
        if prs or self.api.pr_coverage() is not None:
            out += [f"## Pull requests that close it ({len(prs)})"] + self._pr_lines(prs, t) + [""]
        out += [f"## Commits referencing it or brought in by its pull requests ({len(commits)})"]
        out += [f"- `{self.idx.props[c].get('short_hash', '')}` {self.idx.props[c].get('date', '')} {(self.idx.props[c].get('subject') or '')[:90]}"
                for c in commits[:15]]
        out += ["", f"## Module-level functions those commits changed, still present ({len(changed)})"]
        out += [f"- `{self.api._key(i)}` (changed in `{h}`) — `{self.def_line(i)}`" for i, h in sorted(changed.items(), key=lambda p: self.api._key(p[0]))]
        out += ["", f"## Test files that call them ({len(tests)})"] + self._tests_section(tests)
        out += ["", "## Coverage", self.coverage(sorted(changed, key=self.api._key), set(tests))]
        if self.api.pr_coverage() is not None:
            out += ["", "Pull-request links: " + self._pr_coverage_text(self.api._pr_unverified(t, prs))]
        return "\n".join(out + ["", HOW_TO_USE])

    def pr(self, number: str) -> str:
        """A pull request: its commits, the functions it changed, the tests that call them, the issues it closes."""
        p, err = self.api._pr_ref(number)
        if err:
            gh = self.idx.github
            hint = ("" if gh and gh.get("status") == "ok" else
                    " It may be a rebase merge, which leaves no trace in git (build with --github), or outside the history the graph covers.")
            return f"# Graph pack: pull request {number}\n\nThe graph has no pull request {number}.{hint} Search the history."
        props = self.idx.props[p]
        commits = sorted(set(self.idx.targets("MERGES", p)), key=lambda c: (self.idx.props[c].get("date", ""), self.api._key(c)))
        closes = sorted(set(self.idx.targets("CLOSES", p)), key=self.api._key)
        changed = self._changed_by(self._pr_commits_to_read([p]))
        tests = self.tests(set(changed))
        facts = [f"{k}: {props[k]}" for k in ("state", "merge_style", "merged_at", "base", "head", "url") if props.get(k)]
        out = [f"# Graph pack: pull request {self.api._key(p)} ({(props.get('title') or '')[:90]})", "",
               self.freshness(sorted({self.api._key(i).split('::')[0] for i in changed})), "", "; ".join(facts) + ".",
               "", f"## Commits it brought in ({len(commits)})"]
        for c in commits[:25]:
            conf = self.api._link("MERGES", p, c)[0]
            out.append(f"- `{self.idx.props[c].get('short_hash', '')}` {self.idx.props[c].get('date', '')} "
                       f"{(self.idx.props[c].get('subject') or '')[:90]} (confidence {conf})")
        if len(commits) > 25:
            out.append(f"- … {len(commits) - 25} more")
        if not commits:
            out.append("- none in the graph")
        out += ["", f"## Issues it closes ({len(closes)})"]
        for t in closes:
            conf, unv = self.api._link("CLOSES", p, t)
            out.append(f"- `{self.api._key(t)}` {(self.idx.props[t].get('title') or '')[:80]} (confidence {conf}"
                       + (", **unverified**: offline, the number may be a pull request" if unv else "") + ")")
        if not closes:
            out.append("- none in the graph")
        out += ["", f"## Module-level functions it changed, still present ({len(changed)})"]
        out += [f"- `{self.api._key(i)}` (changed in `{h}`) — `{self.def_line(i)}`" for i, h in sorted(changed.items(), key=lambda x: self.api._key(x[0]))]
        out += ["", f"## Tests to run: test files that call them ({len(tests)})"] + self._tests_section(tests)
        if tests:
            out += ["", f"Run: `{self._run(list(tests))}`"]
        out += ["", "## Coverage", self.coverage(sorted(changed, key=self.api._key), set(tests)),
                "", "Pull-request links: " + self._pr_coverage_text([self.api._key(t) for t in closes if self.api._link("CLOSES", p, t)[1]])]
        return "\n".join(out + ["", HOW_TO_USE])

    def commit_trace(self, commit: str) -> str:
        """A commit's ticket, that ticket's epic and specification, as the graph records them."""
        cands = [i for (typ, k), i in self.idx.by_key.items() if typ == "Commit" and k.startswith(commit)]
        if len(cands) != 1:
            return f"# Graph pack: commit {commit}\n\nThe graph has no single commit `{commit}`. Search the history."
        c = cands[0]
        tickets = sorted({self.api._key(x) for x in self.idx.targets("REFERENCES", c)})
        out = [f"# Graph pack: commit `{commit}` — {(self.idx.props[c].get('subject') or '')[:90]}", "",
               f"Built from the dev-process graph at commit `{self.idx.git_head[:10]}`.", "", f"## Tickets it references ({len(tickets)})"]
        for tk in tickets:
            ti = self.idx.node("Ticket", tk)
            epics = [self.api._key(x) for x in self.idx.targets("CHILD_OF", ti)]
            specs = [self.idx.props[x].get("spec_id") or self.api._key(x) for x in self.idx.targets("IMPLEMENTS", ti)]
            out.append(f"- `{tk}`: epic {', '.join(f'`{e}`' for e in epics) or 'not in the graph'}; "
                       f"specification {', '.join(f'`{s}`' for s in specs) or 'not in the graph'}")
        if not tickets:
            out.append("- none in the graph")
        out += ["", "## Coverage", "Links come from the ticket's own Trace table as the graph extracted it; 'not in the graph' means "
                "the link was not extracted, not that it does not exist: read the ticket file for it."]
        return "\n".join(out + ["", HOW_TO_USE])


HOW_TO_USE = ("---\nThis pack was extracted from the source by the dev-process graph; each item carries the line that proves it. "
              "Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the "
              "answer is incomplete.")


def main() -> int:
    ap = argparse.ArgumentParser(description="write a predefined graph pack")
    ap.add_argument("--project", required=True)
    ap.add_argument("kind", choices=("file", "error", "change", "refactor", "ticket", "pr"))
    ap.add_argument("subject", nargs="+")
    ap.add_argument("--role", default="")
    ap.add_argument("--path", default="")
    ns = ap.parse_args()
    try:
        p = Packer(ProcessAPI(ns.project, telemetry=False))
    except GraphNotBuilt as e:
        print(f"devkb pack: {e}", file=sys.stderr)
        return 2
    subject = " ".join(ns.subject)
    print({"file": lambda: p.file(subject), "error": lambda: p.error(subject), "change": lambda: p.change(subject, ns.path),
           "refactor": lambda: p.refactor(subject, ns.role, ns.path), "ticket": lambda: p.ticket(subject),
           "pr": lambda: p.pr(subject)}[ns.kind]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
