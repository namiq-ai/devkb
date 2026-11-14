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
  python3 devkb/packs.py --project OCO pr 42              a pull request's commits, changed functions, tests, closed issues
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.process_api import ProcessAPI, is_test_path  # noqa: E402

MAX_DEPTH = 6


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
        c = self.api._coverage(syms, shown)
        if c.get("complete"):
            return "**Complete.** Every call site under these names was attributed to its target; nothing else calls them."
        files = ", ".join(f"`{f}`" for f in c.get("search_files", [])) or "(files not recorded)"
        shared = f" {c['shared_by']} symbols share the name, so most may be calls to the others." if c.get("shared_by") else ""
        return (f"**Incomplete: {c['unresolved_calls']} call site(s) under this name could not be attributed.**{shared} "
                f"Search only these files for them: {files}.")

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
            cands = [s for s in self.idx.short.get(name, []) if self.api._key(s).startswith(path + "::")]
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

    def refactor(self, name: str, role: str = "", path: str = "") -> str:
        i, err = self.api._resolve(f"{path}::{name}" if path and "::" not in name else name)
        if i is None:
            cands = [s for s in self.idx.short.get(name, []) if not path or self.api._key(s).startswith(path + "::")]
            i = cands[0] if len(cands) == 1 else None
        if i is None:
            return f"# Graph pack: refactor\n\nThe graph cannot resolve `{name}` unambiguously. Search the code."
        callers = sorted(set(self.idx.sources("CALLS", i)), key=self.api._key)
        by_file: dict[str, list[int]] = {}
        for c in callers:
            by_file.setdefault(self.api._key(c).split("::")[0], []).append(c)
        own = self.api._key(i).split("::")[0]
        dnt = self.api._role_table().get(role, {}).get("dnt", []) if role else []
        blocked = sorted(f for f in by_file if any(f.startswith(p) for p in dnt))
        tests = sorted(f for f in by_file if is_test_path(f))
        out = [f"# Graph pack: changing the signature of `{self.api._key(i)}`" + (f" as role {role}" if role else ""), "",
               self.freshness(sorted(by_file)), "", f"Defined at `{self.def_line(i)}`.", "",
               f"## Files with a direct caller ({len(by_file)}, tests included)"]
        for f in sorted(by_file):
            c = by_file[f][0]
            more = f" (+{len(by_file[f]) - 1} more)" if len(by_file[f]) > 1 else ""
            out.append(f"- `{f}`{more} — `{self.call_site(c, self._name(i))}`")
        out += ["", f"## Test files among them ({len(tests)})"] + ([f"- `{f}`" for f in tests] or ["- none"])
        if role:
            out += ["", f"## Files role {role} must not edit ({len(blocked)})"] + ([f"- `{f}`" for f in blocked] or ["- none"])
        if own not in by_file:
            out += ["", f"(The defining file `{own}` is not counted as a caller.)"]
        out += ["", "## Coverage", self.coverage([i], set(by_file))]
        return "\n".join(out + ["", HOW_TO_USE])


    # ── ADDENDUM-1 S2: process joins (ODSF-316) ────────────────────────────────
    def ticket(self, ticket_id: str) -> str:
        """A ticket's commits, the module-level functions they changed that exist now, and the tests that call them."""
        t = self.idx.node("Ticket", ticket_id)
        if t is None:
            return f"# Graph pack: ticket {ticket_id}\n\nThe graph has no ticket {ticket_id}. Search the history."
        commits = sorted(set(self.api._ticket_commits(t)), key=lambda c: self.idx.props[c].get("date", ""))
        prs = self.api._ticket_prs(t)
        changed: dict[int, str] = {}
        for c in commits:
            r = self.api.review_pack(self.api._key(c)[:12])
            for key in r.get("changed_symbols", []):
                path, _, qual = key.partition("::")
                i = self.idx.node("Symbol", key)
                if i is not None and "." not in qual and not is_test_path(path) and self.idx.props[i].get("kind") == "function":
                    changed.setdefault(i, self.idx.props[c].get("short_hash", self.api._key(c)[:10]))
        tests = self.tests(set(changed))
        out = [f"# Graph pack: ticket {ticket_id} ({(self.idx.props[t].get('title') or '')[:90]})", "",
               self.freshness(sorted({self.api._key(i).split('::')[0] for i in changed})), ""]
        if prs:
            out += [f"## Pull requests that close it ({len(prs)})"]
            out += [f"- `{self.api._key(pr)}` {self.idx.props[pr].get('state') or ''}: {(self.idx.props[pr].get('title') or '')[:80]}"
                    + (" — **unverified** (closing keyword in a commit message; #N may be a pull request)" if (pr, t) in self.idx.unverified else "")
                    for pr in prs[:15]]
            out.append("")
        out += [f"## Commits referencing it, or merged by a pull request that closes it ({len(commits)})"]
        out += [f"- `{self.idx.props[c].get('short_hash', '')}` {self.idx.props[c].get('date', '')} {(self.idx.props[c].get('subject') or '')[:90]}"
                for c in commits[:15]]
        out += ["", f"## Module-level functions those commits changed, still present ({len(changed)})"]
        out += [f"- `{self.api._key(i)}` (changed in `{h}`) — `{self.def_line(i)}`" for i, h in sorted(changed.items(), key=lambda p: self.api._key(p[0]))]
        out += ["", f"## Test files that call them ({len(tests)})"] + self._tests_section(tests)
        out += ["", "## Coverage", self.coverage(sorted(changed, key=self.api._key), set(tests))]
        out += self._links_coverage(sum(1 for pr in prs if (pr, t) in self.idx.unverified))
        return "\n".join(out + ["", HOW_TO_USE])

    def _links_coverage(self, unverified: int = 0) -> list[str]:
        """The pull-request and issue links' own coverage, in words (empty for a graph that has no pull requests)."""
        cov = self.api._pr_coverage(unverified)
        if cov is None:
            return []
        if cov["complete"]:
            return ["", "Pull-request and issue links: **complete**, read from GitHub."]
        return ["", "Pull-request and issue links: **incomplete.** " + " ".join(f"{n}." if not n.endswith(".") else n for n in cov["links"])]

    def pr(self, ref: str) -> str:
        """A pull request's commits, the module-level functions it changed that exist now, the tests that call them, the issues it closes."""
        pr, err = self.api._pr(ref)
        if pr is None:
            return f"# Graph pack: pull request {ref}\n\n{err['error']}. Search the history."
        p = self.idx.props[pr]
        commits = sorted(set(self.idx.targets("MERGES", pr)), key=lambda c: (self.idx.props[c].get("date", ""), self.api._key(c)))
        closes = sorted(set(self.idx.targets("CLOSES", pr)), key=self.api._key)
        changed: dict[int, str] = {}
        rng = self.api.pr_range(pr)
        r = self.api.review_pack(rng, 400) if rng else {}
        for key in r.get("changed_symbols", []):
            path, _, qual = key.partition("::")
            i = self.idx.node("Symbol", key)
            if i is not None and "." not in qual and not is_test_path(path) and self.idx.props[i].get("kind") == "function":
                changed[i] = self.api._key(pr)
        tests = self.tests(set(changed))
        out = [f"# Graph pack: {self.api._key(pr)} ({(p.get('title') or '')[:90]})", "",
               self.freshness(sorted({self.api._key(i).split('::')[0] for i in changed})), "",
               f"State: {p.get('state')}" + (f", merged {str(p.get('merged_at'))[:10]}" if p.get("merged_at") else "")
               + (f", {p.get('merge_style')} merge" if p.get("merge_style") else "") + (f", `{p['head']}` into `{p['base']}`" if p.get("head") and p.get("base") else "")
               + (f" — {p['url']}" if p.get("url") else ""), "",
               f"## Commits ({len(commits)})"]
        out += [f"- `{self.idx.props[c].get('short_hash', '')}` {(self.idx.props[c].get('subject') or '')[:90]}" for c in commits[:15]]
        if not commits:
            out.append("- none the graph links (the commits are not in git history, or the pull request was not merged)")
        out += ["", f"## Issues it closes ({len(closes)})"]
        out += [f"- `{self.api._key(t)}` {(self.idx.props[t].get('title') or '')[:80]}"
                + (" — **unverified** (closing keyword in a commit message; #N may be a pull request)" if (pr, t) in self.idx.unverified else "")
                for t in closes] or ["- none the graph records"]
        out += ["", f"## Module-level functions it changed, still present ({len(changed)})"]
        out += [f"- `{self.api._key(i)}` — `{self.def_line(i)}`" for i in sorted(changed, key=self.api._key)] or ["- none"]
        out += ["", f"## Test files that call them ({len(tests)})"] + self._tests_section(tests)
        if tests:
            out += ["", f"Run: `{self._run(list(tests))}`"]
        out += ["", "## Coverage", self.coverage(sorted(changed, key=self.api._key), set(tests))]
        out += self._links_coverage(sum(1 for t in closes if (pr, t) in self.idx.unverified))
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
    ap.add_argument("kind", choices=("error", "change", "refactor", "ticket", "pr"))
    ap.add_argument("subject", nargs="+")
    ap.add_argument("--role", default="")
    ap.add_argument("--path", default="")
    ns = ap.parse_args()
    p = Packer(ProcessAPI(ns.project, telemetry=False))
    subject = " ".join(ns.subject)
    print({"error": lambda: p.error(subject), "change": lambda: p.change(subject, ns.path),
           "refactor": lambda: p.refactor(subject, ns.role, ns.path), "ticket": lambda: p.ticket(subject),
           "pr": lambda: p.pr(subject)}[ns.kind]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
