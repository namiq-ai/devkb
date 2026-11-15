#!/usr/bin/env python3
"""Software-engineering-process questions over the devkb graph (ODSF-306).

Each method answers one question a development stage asks and returns a short
JSON-able dict: ids and paths, not node dumps. Every reply carries `_meta`
(when the graph was built, at which commit, whether the repository has moved
on) so a caller can tell a fresh answer from a stale one.

  python3 devkb/process_api.py --project ODSF graph-status
  python3 devkb/process_api.py --project ODSF callers _load_process depth=2
  python3 devkb/process_api.py --project ODSF tests-to-run files=devkb/build_symbols.py
  python3 devkb/process_api.py --project ODSF bench

Stage map (the AI SDLC playbook, S0 to S10): sdlc_context and find_docs serve
S0-S4, trace serves S5-S6, symbol/callers/callees/tests_for/impact/tests_to_run/
owner serve S1 and S7, review_pack serves S8, lineage serves S9-S10.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.project_context import CONFIG_FILES, registry, resolve, run_repo_scripts  # noqa: E402
from devkb.service import CompactIndex, Staleness, Telemetry, load_index, words  # noqa: E402
from devkb.test_discovery import _JS_TEST, _PY_TEST  # noqa: E402

_TICKET_ID = re.compile(r"\b[A-Z][A-Z0-9]{1,6}-\d+\b")
# ODSF writes `### OWN:`; OCO writes `### YOU OWN:`, `### YOU OWN (read + write freely):` or `### TL OWNS:`.
_OWN = re.compile(r"### (?:YOU OWN|OWN|[A-Z]{2,3} OWNS)\b[^\n]*:\s*```[\w]*\n(.*?)```", re.DOTALL)
_DNT = re.compile(r"### DO NOT TOUCH:\s*```[\w]*\n(.*?)```", re.DOTALL)
_HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


REPLY_BUDGET_BYTES = 3900
# Words that carry no meaning in a request ("add a report for the specs"). Without this, "add" matches every method called add.
STOP = frozenset("the and for add with that this from into how new use when why not are can has have was but its any all".split())


def query_words(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOP]


def _fit(reply: dict, budget: int = REPLY_BUDGET_BYTES) -> dict:
    """Keep a reply under `budget` bytes by halving its longest list until it fits, and say what was left out.
    A `limit` caps one list; a reply with two long lists (callers and indirect callers of a hub class) still
    overran 4 KB, so the size itself is now enforced (ODSF-309). Totals such as `n` stay exact."""
    omitted: dict[str, int] = {}

    def size() -> int:
        return len(json.dumps(reply, separators=(",", ":")))

    while size() > budget:
        lists = [(k, v) for k, v in reply.items() if isinstance(v, list) and len(v) > 3]
        if not lists:
            break
        key, items = max(lists, key=lambda kv: len(json.dumps(kv[1], separators=(",", ":"))))
        keep = max(3, len(items) // 2)
        omitted[key] = omitted.get(key, 0) + len(items) - keep
        reply[key] = items[:keep]
    if omitted:
        reply["truncated"] = True
        reply["omitted"] = omitted
    return reply


_GENERATED = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|Cargo\.lock)$|"
                        r"\.min\.(js|css)$|(^|/)(dist|build|node_modules|__pycache__|\.next[^/]*)/")


def is_generated_path(path: str) -> bool:
    """Lockfiles, minified and built output: never a place to read or edit, so never listed in an answer (ODSF-313)."""
    return bool(_GENERATED.search(path))


_TEST_TREE = re.compile(r"(^|/)(tests?/[^/].*\.py|conftest\.py)$")


def is_test_path(path: str) -> bool:
    """Test code: a test module by name, or any Python file in a tests/ or test/ tree (fixtures, helpers, conftest),
    since a change that breaks those breaks the test run just the same."""
    return bool(_PY_TEST.search(path) or _JS_TEST.search(path) or _TEST_TREE.search(path))


def _lines(block: str) -> list[str]:
    """Paths from a profile's fenced block. An indented line is relative to the directory line above it (OCO writes
    `scripts/` then `  extractors/extract_*.py`); a glob is cut to the prefix before its first `*`; comments after
    `←`, `→`, `#` or `,` are dropped."""
    out: list[str] = []
    parents: list[tuple[int, str]] = []
    for line in block.splitlines():
        clean = re.split(r"[←→#,]|\s{2,}", line.strip())[0].strip()
        if not clean:
            continue
        indent = len(line) - len(line.lstrip())
        while parents and parents[-1][0] >= indent:
            parents.pop()
        full = (parents[-1][1] if parents else "") + clean
        if clean.endswith("/"):
            parents.append((indent, full))
        full = full.split("*", 1)[0]
        if full and full not in out:
            out.append(full)
    # A directory line with lines indented under it is a heading for them, not a claim on the whole directory.
    return [p for p in out if not (p.endswith("/") and any(q != p and q.startswith(p) for q in out))]


def project_for(cwd: Path) -> str | None:
    """The registered project whose repository contains `cwd`, so a daemon job started in a
    project's checkout needs no project argument. The deepest match wins."""
    best, code = -1, None
    for entry in registry():
        try:
            repo = Path(entry["repo"]).resolve()
            cwd.resolve().relative_to(repo)
        except (KeyError, ValueError, OSError):
            continue
        if len(str(repo)) > best:
            best, code = len(str(repo)), entry.get("code")
    return code


class ProcessAPI:
    def __init__(self, code: str, use_cache: bool = True, telemetry: bool = True, devkb_dir: Path | None = None) -> None:
        """`devkb_dir` (or the DEVKB_DIR environment variable) points at a pinned graph
        snapshot instead of the project's live `.devkb/`, which any build overwrites.
        The benchmark relies on this so every run reads the same graph. DEVKB_REPO points at the
        checkout that snapshot was built from, so history, diffs and staleness are read there too."""
        # ODSF-315: an explicitly external repository (a public project in a benchmark), never a silent default
        if os.environ.get("DEVKB_EXTERNAL") == "1" and os.environ.get("DEVKB_REPO") and os.environ.get("DEVKB_DIR"):
            from devkb.project_context import external_context  # noqa: PLC0415
            self.ctx = external_context(code, Path(os.environ["DEVKB_REPO"]), Path(os.environ["DEVKB_DIR"]))
        else:
            self.ctx = resolve(code)
        self.root: Path = Path(os.environ["DEVKB_REPO"]).resolve() if os.environ.get("DEVKB_REPO") else self.ctx.repo_root
        store = devkb_dir or (Path(os.environ["DEVKB_DIR"]) if os.environ.get("DEVKB_DIR") else self.ctx.devkb_dir)
        self.idx: CompactIndex = load_index(self.ctx.code, self.root, store, use_cache)
        self.stale = Staleness(self.root, self.idx.git_head)
        self.tel = Telemetry(store, telemetry)
        self._roles: dict[str, dict[str, list[str]]] | None = None
        self._roles_key: tuple | None = None
        self._cfg: dict = {}
        self._cfg_stamp: tuple | None = None
        self._moved_cache: dict[str, set[str]] = {}
        self._fn_cache: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
        self._bmad_status: tuple | None = None
        self._written: dict[tuple, str] = {}  # (doc, mtime, graph head) -> date of the doc's last commit

    # ── plumbing ───────────────────────────────────────────────────────────
    def call(self, tool: str, **kw) -> dict:
        t0 = time.perf_counter()
        ok = True
        try:
            reply = getattr(self, tool)(**kw)
        except TypeError as exc:
            reply, ok = {"error": f"bad arguments for {tool}: {exc}"}, False
        if "error" in reply:
            ok = False
        else:
            if os.environ.get("DEVKB_NO_COVERAGE") == "1":  # ODSF-316 ablation only: the reply as it was before ODSF-313
                reply.pop("coverage", None)
            reply = _fit(reply)
        stale, head, behind = self.stale.check()
        reply["_meta"] = {"built": self.idx.built_at[:16], "head": self.idx.git_head[:8], "stale": stale,
                          **({"behind": behind} if stale else {})}
        size = len(json.dumps(reply, separators=(",", ":")))
        self.tel.log(tool, (time.perf_counter() - t0) * 1000, size, ok)
        return reply

    def _key(self, i: int) -> str:
        return self.idx.keys[i]

    def _resolve(self, ref: str) -> tuple[int | None, dict | None]:
        idx = self.idx
        if "::" in ref:
            i = idx.node("Symbol", ref)
            return (i, None) if i is not None else (None, {"error": f"no symbol {ref}"})
        cands = idx.short.get(ref.rsplit(".", 1)[-1], [])
        if len(cands) == 1:
            return cands[0], None
        if not cands:
            return None, {"error": f"no symbol named {ref}"}
        return None, {"error": f"{len(cands)} symbols named {ref}; pass one as path::name",
                      "matches": [self._key(c) for c in cands[:8]]}

    def _file_symbols(self, ref: str) -> list[int]:
        return self.idx.sym_by_file.get(ref, [])

    def _callers(self, start: set[int], depth: int) -> list[list[int]]:
        """Reverse CALLS BFS: one list of symbol indexes per depth level."""
        seen = set(start)
        frontier = set(start)
        levels: list[list[int]] = []
        for _ in range(depth):
            nxt: set[int] = set()
            for s in frontier:
                for c in self.idx.sources("CALLS", s):
                    if c not in seen:
                        seen.add(c)
                        nxt.add(c)
            levels.append(sorted(nxt, key=lambda i: (is_test_path(self._key(i).split("::")[0]), self._key(i))))
            frontier = nxt
        return levels

    def _tests_of(self, syms: list[int]) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for s in syms:
            for tc in self.idx.targets("TESTED_BY", s):
                p = self.idx.props[tc]
                if p.get("file"):
                    found.setdefault(p["file"], set()).add(p.get("function", "?"))
            for c in self.idx.sources("CALLS", s):
                path, _, qual = self._key(c).partition("::")
                if is_test_path(path):
                    found.setdefault(path, set()).add(qual.rsplit(".", 1)[-1])
        return found

    @staticmethod
    def _run_line(files: list[str]) -> str:
        py = [f for f in files if f.endswith(".py")]
        return ("python3 -m pytest " + " ".join(py) + " -q") if py else ""

    def _config(self) -> dict:
        """The project's devkb.json (or pms.config.json), parsed again only when the file changed."""
        path = next((self.root / n for n in CONFIG_FILES if (self.root / n).is_file()), self.root / CONFIG_FILES[0])
        try:
            st = path.stat()
        except OSError:
            return {}
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp != self._cfg_stamp:
            try:
                self._cfg = json.loads(path.read_text())
            except (OSError, ValueError):
                self._cfg = {}
            self._cfg_stamp = stamp
        return self._cfg

    def _roles_dir(self) -> Path:
        return self.root / str(self._config().get("roles_dir") or "sdp/process/roles")

    def _role_file(self, code: str) -> str | None:
        return self._role_file_in(self.root, self._config(), code)

    @staticmethod
    def _role_file_in(root: Path, cfg: dict, code: str) -> str | None:
        """A role's profile file in the roles directory: `<code>.md` or the first `<code>-*.md`, case-insensitive."""
        try:
            names = sorted(p.name for p in (root / str(cfg.get("roles_dir") or "sdp/process/roles")).glob("*.md"))
        except OSError:
            return None
        return next((n for n in names if n.lower().startswith(code.lower() + "-") or n.lower() == code.lower() + ".md"), None)

    def _profiles(self) -> dict[str, str]:
        """Role code -> profile file. A project that declares no `role_profiles` (OCO) still has a roster in
        `team_roles` and the factory's default file names; project_paths is the one place that says so (ODSF-095)."""
        declared = self._config().get("role_profiles")
        if isinstance(declared, dict) and declared:
            return {str(k): str(v) for k, v in declared.items()}
        roster = self._config().get("team_roles")
        if not isinstance(roster, list) or not roster:
            return {}
        return {str(c).strip().upper(): f for c in roster if (f := self._role_file(str(c).strip().upper()))}

    def _role_table(self) -> dict[str, dict[str, list[str]]]:
        roles_dir = self._roles_dir()
        try:
            key = (self._cfg_stamp if self._config() is not None else None, roles_dir.stat().st_mtime_ns)
        except OSError:
            key = (self._cfg_stamp, None)
        if self._roles is not None and self._roles_key == key:
            return self._roles
        table: dict[str, dict[str, list[str]]] = {}
        profiles = self._profiles()
        for code, fname in profiles.items():
            try:
                text = (self._roles_dir() / str(fname)).read_text()
            except OSError:
                continue
            own, dnt = _OWN.search(text), _DNT.search(text)
            table[code] = {"own": _lines(own.group(1)) if own else [], "dnt": _lines(dnt.group(1)) if dnt else []}
        self._roles, self._roles_key = table, key
        return table

    # ── S1, S7: the code and its surroundings ──────────────────────────────
    def graph_status(self) -> dict:
        c = self.idx.type_count
        return {"project": self.idx.code, "nodes": len(self.idx.keys), "edges": self.idx.n_edges,
                "symbols": c.get("Symbol", 0), "tests": c.get("TestCase", 0), "specs": c.get("Spec", 0),
                "tickets": c.get("Ticket", 0)}

    def symbol(self, name: str, limit: int = 8) -> dict:
        found = self.idx.short.get(name.rsplit(".", 1)[-1], [])
        return {"name": name, "n": len(found),
                "symbols": [{"k": self._key(i), "kind": self.idx.props[i].get("kind"),
                             "line": self.idx.props[i].get("line_start")} for i in found[:limit]]}

    # ── ODSF-313: say what an answer cannot see, so a partial list never looks complete ──
    def _coverage(self, syms, shown: set[str] | None = None) -> dict:
        """Call sites the resolver left unattributed under these symbols' names, and the files holding them. When
        several symbols share a name, an unresolved call may belong to any of them; `shared_by` says how many."""
        names: dict[str, int] = {}
        files: dict[str, None] = {}
        n = 0
        file_total = 0
        for s in syms:
            name = self._key(s).split("::")[-1].split(".")[-1]
            if name in names:
                continue
            p = self.idx.props[s]
            names[name] = len(self.idx.short.get(name, []))
            n += int(p.get("unresolved_calls") or 0)
            listed = p.get("unresolved_files") or []
            file_total += int(p.get("unresolved_file_count") or len(listed)) - sum(1 for f in listed if shown and f in shown)
            for f in listed:
                if not shown or f not in shown:
                    files[f] = None
        if not n:
            return {"complete": True}
        shared = max(names.values(), default=1)
        # search_files is the first 10 by call count; search_file_count says how many files hold such calls in all.
        more = {"search_file_count": file_total} if file_total > min(len(files), 10) else {}
        if not files and any(self.idx.props[s].get("unresolved_files") for s in syms):
            more["in_listed_files"] = True  # every such call is in a file the answer already lists
        return {"complete": False, "unresolved_calls": n, "search_files": list(files)[:10], **more,
                **({"shared_by": shared, "note": f"{shared} symbols share this name; most of these calls may be to the others"}
                   if shared > 3 else {})}

    def callers(self, symbol: str, depth: int = 1, limit: int = 25) -> dict:
        i, err = self._resolve(symbol)
        if err:
            return err
        levels = self._callers({i}, max(1, min(int(depth), 3)))
        out = {"symbol": self._key(i), "n": [len(lv) for lv in levels]}
        out["direct"] = [self._key(c) for c in levels[0][:limit]]
        if len(levels) > 1:
            out["indirect"] = [self._key(c) for lv in levels[1:] for c in lv[:limit]][:limit]
        if len(levels[0]) > limit:
            out["truncated"] = True
        at_module = self.idx.props[i].get("module_callers") or []
        if at_module:  # calls outside any function: no caller symbol, only the file
            out["module_level_files"] = list(at_module)[:limit]
        out["coverage"] = self._coverage([i], {self._key(c).split("::")[0] for c in levels[0]} | set(at_module))
        return out

    def callees(self, symbol: str, limit: int = 25) -> dict:
        i, err = self._resolve(symbol)
        if err:
            return err
        t = sorted({self._key(c) for c in self.idx.targets("CALLS", i)})
        return {"symbol": self._key(i), "n": len(t), "callees": t[:limit], **({"truncated": True} if len(t) > limit else {})}

    def tests_for(self, ref: str, limit: int = 10) -> dict:
        syms = self._file_symbols(ref)
        if not syms:
            i, err = self._resolve(ref)
            if err:
                return err
            syms = [i]
        found = self._tests_of(syms)
        files = sorted(found, key=lambda f: (-len(found[f]), f))
        cov = self._coverage(syms, set(files)) if len(syms) <= 3 else {}
        return {"for": ref, "n_files": len(files), "n_tests": sum(len(v) for v in found.values()),
                "files": [{"f": f, "t": sorted(found[f])[:5]} for f in files[:limit]],
                "run": self._run_line(files[:limit]),
                **({"coverage": {k: v for k, v in cov.items() if k != "search_files"} | {"search_files": [f for f in cov.get("search_files", []) if is_test_path(f)]}}
                   if cov else {})}

    def tests_to_run(self, files: list[str] | str, limit: int = 12) -> dict:
        files = [files] if isinstance(files, str) else list(files)
        hits: dict[str, int] = {}
        for f in files:
            if is_test_path(f):
                hits[f] = hits.get(f, 0) + 100
                continue
            for tf, names in self._tests_of(self._file_symbols(f)).items():
                hits[tf] = hits.get(tf, 0) + len(names)
        ranked = sorted(hits, key=lambda f: (-hits[f], f))
        known = sum(1 for f in files if self._file_symbols(f) or is_test_path(f))
        return {"changed": len(files), "known_to_graph": known, "n": len(ranked), "tests": ranked[:limit],
                "run": self._run_line(ranked[:limit]),
                **({"note": "no tests linked; run the full suite"} if not ranked else {})}

    def impact(self, files: list[str] | str, depth: int = 2, limit: int = 12) -> dict:
        files = [files] if isinstance(files, str) else list(files)
        changed = {s for f in files for s in self._file_symbols(f)}
        levels = self._callers(changed, max(1, min(int(depth), 3)))
        file_set = set(files)
        affected = [c for lv in levels for c in lv if self._key(c).split("::")[0] not in file_set
                    and not is_generated_path(self._key(c).split("::")[0])]
        by_file: dict[str, int] = {}
        for c in affected:
            by_file[self._key(c).split("::")[0]] = by_file.get(self._key(c).split("::")[0], 0) + 1
        keys = {self._key(s) for s in changed} | {self._key(c) for c in affected}
        endpoints = sorted({self._key(e) for k in keys for e in self.idx.ep_by_owner.get(k, [])})
        flows = sorted({self._key(f) for s in changed | set(affected) for f in self.idx.sources("STEP", s)})
        tests = self.tests_to_run(files, limit=8)
        return {"files": len(files), "changed_symbols": len(changed), "affected_symbols": len(affected),
                "affected_files": [{"f": f, "n": n} for f, n in sorted(by_file.items(), key=lambda p: -p[1])[:limit]],
                "endpoints": endpoints[:8], "n_flows": len(flows), "flows": flows[:4],
                "tests": tests["tests"], "run": tests["run"], "owners": self._owners_of(files),
                "coverage": self._coverage(sorted(changed)[:40], set(by_file)) if changed else {"complete": True}}

    # ── S7: the fence ──────────────────────────────────────────────────────
    def _owners_of(self, files: list[str]) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = {}
        for code, spec in self._role_table().items():
            for f in files:
                if any(f.startswith(p) for p in spec["own"]):
                    owners.setdefault(code, []).append(f)
        return {k: sorted(v)[:4] for k, v in owners.items()}

    def owner(self, path: str) -> dict:
        roles = self._role_table()
        own = [(len(p), code) for code, s in roles.items() for p in s["own"] if path.startswith(p)]
        own.sort(reverse=True)
        forbidden = sorted({code for code, s in roles.items() if any(path.startswith(p) for p in s["dnt"])})
        sub = ""
        for s in sorted(self._config().get("subsystems", []), key=lambda s: -len(s.get("path", ""))):
            if s.get("path") and path.startswith(s["path"]):
                sub = s["key"]
                break
        return {"path": path, "owner": sorted({c for _, c in own[:1]}) if own else [], "forbidden_for": forbidden,
                "subsystem": sub, **({"note": "no role owns this path; TL decides"} if not own else {})}

    # ── S0 to S6: the requirement chain ────────────────────────────────────
    def _ticket(self, ticket: str) -> tuple[int | None, dict | None]:
        t = self.idx.node("Ticket", ticket)
        return (t, None) if t is not None else (None, {"error": f"no ticket {ticket}"})

    # ── pull requests and hosted issues (ADR-DEVKB-007) ──────────────────────────────────────
    def _link(self, verb: str, p: int, other: int) -> tuple[float | None, bool]:
        """(confidence, unverified) of a MERGES or CLOSES edge."""
        return self.idx.link_meta.get((verb, p, other), (None, False))

    def _pr_row(self, p: int, verb: str = "", other: int | None = None) -> dict:
        props = self.idx.props[p]
        row = {"id": self._key(p), "title": (props.get("title") or "")[:90], "state": props.get("state")}
        if props.get("merged_at"):
            row["merged_at"] = str(props["merged_at"])[:10]
        if verb and other is not None:
            conf, unverified = self._link(verb, p, other)
            if conf is not None and conf < 1.0:
                row["confidence"] = conf
            if unverified:
                row["unverified"] = True
        return row

    def _ticket_prs(self, t: int) -> list[int]:
        return sorted(set(self.idx.sources("CLOSES", t)), key=self._key)

    def _pr_unverified(self, t: int, prs: list[int]) -> list[str]:
        return [self._key(p) for p in prs if self._link("CLOSES", p, t)[1]]

    def pr_coverage(self, unverified: list[str] | None = None) -> dict | None:
        """What the pull-request layer could not see, in the shape of every other `coverage`: None when the
        repository has no GitHub remote and no pull request in its graph, so replies for it are unchanged."""
        gh = self.idx.github
        if not gh and not self.idx.type_count.get("PullRequest"):
            return None
        status = gh.get("status") or "offline"
        unverified = sorted(set(unverified or []))
        cov: dict = {"complete": status == "ok" and not unverified, "github": status}
        if status == "offline":
            cov["note"] = ("pull-request links come from git alone: rebase merges and issues closed by a pull request's "
                           "description are not visible (build with --github)")
        elif status != "ok":
            cov["note"] = (f"GitHub layer {status}: {gh.get('reason') or 'not fetched'}; not fetched: "
                           f"{', '.join(gh.get('not_fetched') or []) or 'everything'}; links shown are the offline ones"
                           + (" and cached data" if gh.get("stale_cache_used") else ""))
        if unverified:
            cov["unverified"] = unverified
            cov.setdefault("note", "offline closing-keyword links whose target may be a pull request, not an issue")
        return cov

    def _with_pr_coverage(self, reply: dict, unverified: list[str] | None = None) -> dict:
        cov = self.pr_coverage(unverified)
        if cov is not None:
            reply["coverage"] = cov
        return reply

    @staticmethod
    def _is_hosted(ticket: str) -> bool:
        return bool(re.fullmatch(r"(?:[A-Za-z0-9_-]+:)?GH-\d+", ticket))

    def _prs_of_commit(self, c: int) -> list[int]:
        return sorted(set(self.idx.sources("MERGES", c)), key=self._key)

    def _pr_ref(self, ref: str) -> tuple[int | None, dict | None]:
        m = re.fullmatch(r"(?i)((?:[A-Za-z0-9_-]+:)?)(?:PR-|#)?(\d+)", str(ref).strip())
        i = self.idx.node("PullRequest", f"{m.group(1)}PR-{m.group(2)}") if m else None
        return (i, None) if i is not None else (None, {"error": f"no pull request {ref}"})

    def pull_request(self, pr: str) -> dict:
        """A pull request: how it was merged, its commits, the issues it closes, and what the graph cannot verify."""
        p, err = self._pr_ref(pr)
        if err:
            return self._with_pr_coverage(err)
        idx, props = self.idx, self.idx.props[p]
        commits = sorted(set(idx.targets("MERGES", p)), key=lambda c: (idx.props[c].get("date", ""), self._key(c)))
        closes = sorted(set(idx.targets("CLOSES", p)), key=self._key)
        out = {"pr": self._key(p), "title": (props.get("title") or "")[:110], "state": props.get("state"),
               "merged_at": props.get("merged_at"), "merge_style": props.get("merge_style"), "base": props.get("base"),
               "head": props.get("head"), "url": props.get("url"),
               "commits": [{"h": idx.props[c].get("short_hash"), "s": (idx.props[c].get("subject") or "")[:72],
                            "c": self._link("MERGES", p, c)[0]} for c in commits[:25]],
               "n_commits": len(commits),
               "closes": [{"id": self._key(t), "title": (idx.props[t].get("title") or "")[:80], "c": self._link("CLOSES", p, t)[0],
                           **({"unverified": True} if self._link("CLOSES", p, t)[1] else {})} for t in closes]}
        return self._with_pr_coverage({k: v for k, v in out.items() if v not in (None, "")},
                                      [self._key(t) for t in closes if self._link("CLOSES", p, t)[1]])

    def sdlc_context(self, ticket: str) -> dict:
        t, err = self._ticket(ticket)
        if err:
            return err
        idx, p = self.idx, self.idx.props[t]
        commits = idx.sources("REFERENCES", t)
        touched: dict[int, int] = {}
        for c in commits:
            for f in idx.targets("TOUCHES", c):
                touched[f] = touched.get(f, 0) + 1
        issues_rel = self.ctx.issues_dir.relative_to(self.root).as_posix() + "/" if self.ctx.issues_dir.is_relative_to(self.root) else "issues/"
        files = [f for f in sorted(touched, key=lambda f: (-touched[f], self._key(f)))
                 if len(idx.sources("TOUCHES", f)) < 150 and not self._key(f).startswith(issues_rel)][:10]
        owner_role = self._config().get("component_to_role", {}).get(p.get("component", ""), "")
        return {"ticket": ticket, "title": (p.get("title") or "")[:110], "type": p.get("ticket_type"), "status": p.get("status"),
                "priority": p.get("priority"), "component": p.get("component"), "assignee": p.get("assignee"),
                "owner_role": owner_role,
                "epic": [self._key(x) for x in idx.targets("CHILD_OF", t)],
                "spec": [self._key(x) for x in idx.targets("IMPLEMENTS", t)],
                "requirement": [self._key(x) for x in idx.targets("DERIVED_FROM", t)],
                "docs": [self._key(x) for x in idx.sources("DOCUMENTS", t)][:5],
                "similar": [{"t": self._key(b), "s": round(s, 2)} for b, s in idx.sim.get(t, [])[:4]],
                "commits": len(commits), "files": [self._key(f) for f in files],
                **({"pull_requests": [self._pr_row(x, "CLOSES", t) for x in self._ticket_prs(t)]} if self._ticket_prs(t) else {})}

    def _bmad_stamp(self) -> tuple:
        """(file count, newest modification) of the BMAD ticket store, so a cached status is dropped when it changes."""
        count = newest = 0
        for dirpath, _dirs, names in os.walk(self.root / "_bmad-output"):
            for name in names:
                try:
                    m = os.stat(os.path.join(dirpath, name)).st_mtime_ns
                except OSError:
                    continue
                count += 1
                newest = max(newest, m)
        script = self.root / "_bmad" / "method" / "scripts" / "tickets.py"
        return (count, newest, script.stat().st_mtime_ns if script.exists() else 0)

    def _bmad_unknown_cached(self, root: Path, ref: str):
        """readiness_gate._bmad_unknown without launching `uv run tickets.py status` on every call (ODSF-309).
        That subprocess took about 280 ms and its answer only changes when a BMAD ticket file does."""
        script = root / "_bmad" / "method" / "scripts" / "tickets.py"
        parts = ref.split("/")
        if not script.exists() or len(parts) != 3:
            return None
        stamp = self._bmad_stamp()
        if self._bmad_status is None or self._bmad_status[0] != stamp:
            try:
                status = json.loads(subprocess.run(["uv", "run", "--no-cache", str(script), "--project-root", str(root), "status"],
                                                   capture_output=True, text=True, timeout=120, check=True).stdout)
            except (OSError, subprocess.SubprocessError, ValueError):
                return None
            self._bmad_status = (stamp, status)
        row = next((t for t in self._bmad_status[1].get("tickets", [])
                    if t.get("epic") == parts[1] and str(t.get("id")) == parts[2]), None)
        return (row or {}).get("unknown") or ""

    def trace(self, ticket: str) -> dict:
        t, err = self._ticket(ticket)
        if err:
            return err
        idx, p = self.idx, self.idx.props[t]

        def link(verb: str) -> list[dict]:
            return [{"id": self._key(x), "status": idx.props[x].get("status")} for x in idx.targets(verb, t)]

        out = {"ticket": ticket, "type": p.get("ticket_type"), "status": p.get("status"), "epic": link("CHILD_OF"),
               "spec": link("IMPLEMENTS"), "requirement": [{"id": self._key(x)} for x in idx.targets("DERIVED_FROM", t)]}
        prs = self._ticket_prs(t)
        if prs:
            out["pull_requests"] = [self._pr_row(x, "CLOSES", t) for x in prs]
        children = sorted(set(idx.sources("CHILD_OF", t)), key=self._key) if self._is_hosted(ticket) else []
        if children:
            out["sub_issues"] = [{"id": self._key(x), "status": idx.props[x].get("status")} for x in children]
        if prs or self._is_hosted(ticket):
            self._with_pr_coverage(out, self._pr_unverified(t, prs))
        if p.get("ticket_type") != "STORY":
            out["gate0"] = "n/a: only STORY tickets are gated"
            return out
        if not run_repo_scripts(self.root):
            out["gate0"] = "n/a: running the repository's readiness gate is off (run_repo_scripts)"
            return out
        try:
            gates = self.root / "sdp" / "devsecops" / "quality-gates"
            for extra in (gates, self.root / "issue-tools", self.root / "scripts"):
                if str(extra) not in sys.path and extra.exists():
                    sys.path.insert(0, str(extra))
            import readiness_gate  # type: ignore
            ipath = self.root / (p.get("issue_path") or "")
            original = readiness_gate._bmad_unknown
            readiness_gate._bmad_unknown = self._bmad_unknown_cached
            try:
                out["gate0"] = readiness_gate.check_story(ipath, self.root, self.root / "issues")
            finally:
                readiness_gate._bmad_unknown = original
        except Exception as exc:  # the verdict is advisory here; the real gate is `make gate-0`
            out["gate0"] = f"unavailable: {type(exc).__name__}"
        return out

    def _doc_score(self, i: int, toks: list[str], idf: dict[str, float], topic_id: str) -> float:
        title_w, path_w, head_w = self.idx.spec_terms[i]
        score = 0.0
        for w in toks:
            score += idf[w] * ((3 if w in title_w else 0) + (2 if w in path_w else 0) + (1 if w in head_w else 0))
        if str(self.idx.props[i].get("spec_id") or "").lower() == topic_id:
            score += 10
        return score

    def _rank_docs(self, topic: str, kinds, candidates) -> list[tuple[float, int]]:
        want = {kinds} if isinstance(kinds, str) else set(kinds or [])
        toks = words(topic)
        n = max(1, len(self.idx.spec_terms))
        idf = {w: math.log((n + 1) / (self.idx.spec_df.get(w, 0) + 1)) + 1 for w in set(toks)}
        topic_id = topic.strip().lower()
        scored = []
        for i in candidates:
            if want and self.idx.props[i].get("doc_type") not in want:
                continue
            score = self._doc_score(i, toks, idf, topic_id)
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda s: (-s[0], self._key(s[1])))
        return scored

    def find_docs(self, topic: str, kinds: list[str] | str | None = None, limit: int = 8) -> dict:
        """Only documents that share a word with the query (or are named by it) are scored, found through
        an inverted index built with the graph; the weights are computed once per query word."""
        cand: set[int] = set()
        for w in set(words(topic)):
            cand.update(self.idx.spec_inv.get(w, ()))
        exact = self.idx.spec_by_id.get(topic.strip().lower())
        if exact is not None:
            cand.add(exact)
        scored = self._rank_docs(topic, kinds, cand)
        return {"topic": topic, "n": len(scored),
                "docs": [{"p": self._key(i), "t": (self.idx.props[i].get("title") or "")[:80],
                          "k": self.idx.props[i].get("doc_type"), "s": self.idx.props[i].get("status"), "sc": round(sc, 1)}
                         for sc, i in scored[:limit]]}

    def _find_docs_scan(self, topic: str, kinds=None, limit: int = 8) -> list[str]:
        """The pre-ODSF-309 behaviour, scoring every document. Kept as the reference the inverted index must match."""
        return [self._key(i) for _, i in self._rank_docs(topic, kinds, self.idx.spec_terms.keys())][:limit]

    # ── S8: review ─────────────────────────────────────────────────────────
    def _git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True).stdout

    @staticmethod
    def _parse_diff(text: str) -> dict[str, list[tuple[int, int]]]:
        files: dict[str, list[tuple[int, int]]] = {}
        cur = ""
        for line in text.splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
                files.setdefault(cur, [])
            elif line.startswith("@@") and cur:
                m = _HUNK.match(line)
                if m:
                    start, n = int(m.group(1)), int(m.group(2) or 1)
                    files[cur].append((start, start + max(n, 1) - 1))
        return files

    def _moved_files(self, head_rev: str) -> set[str]:
        """Files that differ between `head_rev` and the commit the graph was built from: for those, line numbers
        in the diff do not match the graph. One git call for the whole set (it was one call per changed file)."""
        built = self.idx.git_head
        if not built or head_rev == built:
            return set()
        if head_rev not in self._moved_cache:
            if len(self._moved_cache) > 64:
                self._moved_cache.clear()
            self._moved_cache[head_rev] = {ln for ln in self._git("diff", "--name-only", head_rev, built).splitlines() if ln}
        return self._moved_cache[head_rev]

    def _has_tests(self, s: int) -> bool:
        if self.idx.targets("TESTED_BY", s):
            return True
        return any(is_test_path(self._key(c).split("::")[0]) for c in self.idx.sources("CALLS", s))

    def _function_ranges(self, head_rev: str, path: str) -> list[tuple[int, int, str]]:
        """(first line, last line, `Class.method`) for every function in `path` as it was at `head_rev`.
        Parsing a large file costs tens of milliseconds, so the table is kept per (commit, file) (ODSF-309)."""
        key = (head_rev, path)
        if key in self._fn_cache:
            return self._fn_cache[key]
        import ast
        src = self._git("show", f"{head_rev}:{path}")
        ranges: list[tuple[int, int, str]] = []
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            tree = None

        def walk(node: ast.AST, stack: list[str]) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    walk(child, stack + [child.name])
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ranges.append((child.lineno, child.end_lineno or child.lineno, ".".join(stack + [child.name])))
                    walk(child, stack + [child.name])
        if tree is not None:
            walk(tree, [])
        if len(self._fn_cache) > 64:
            self._fn_cache.clear()
        self._fn_cache[key] = ranges
        return ranges

    def _changed_python_names(self, head_rev: str, path: str, hunks: list[tuple[int, int]]) -> list[str]:
        """`Class.method` names of the functions whose lines a diff touched, read from the file as it was
        at `head_rev`, not from the graph, which describes a later commit."""
        return [name for start, end, name in self._function_ranges(head_rev, path)
                if any(h0 <= end and start <= h1 for h0, h1 in hunks)]

    def review_pack(self, rev: str, limit: int = 12) -> dict:
        base, head_rev = rev.split("..", 1) if ".." in rev else (f"{rev}^", rev)
        # Three independent git calls, run together: the diff, the commit subjects, the files moved since the graph.
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_diff = pool.submit(self._git, "diff", "-U0", "--no-color", base, head_rev)
            f_msgs = pool.submit(self._git, "log", "--format=%s", f"{base}..{head_rev}")
            f_moved = pool.submit(self._moved_files, head_rev)
            files, msgs, moved = self._parse_diff(f_diff.result()), f_msgs.result(), f_moved.result()
        if not files:
            return {"error": f"no diff for {rev}"}
        changed: list[int] = []
        drifted: list[str] = []
        unmapped: list[str] = []
        for f, hunks in files.items():
            if f not in moved:
                for s in self._file_symbols(f):
                    p = self.idx.props[s]
                    a, b = p.get("line_start") or 0, p.get("line_end") or 0
                    if any(h0 <= b and a <= h1 for h0, h1 in hunks):
                        changed.append(s)
            elif f.endswith(".py"):
                # The file moved on after this commit: read the commit's own source, then find each function in the graph by name.
                drifted.append(f)
                for name in self._changed_python_names(head_rev, f, hunks):
                    i = self.idx.node("Symbol", f"{f}::{name}")
                    if i is None:
                        unmapped.append(f"{f}::{name}")
                    else:
                        changed.append(i)
        changed_set, file_set = set(changed), set(files)
        outside = [c for lv in self._callers(changed_set, 1) for c in lv if self._key(c).split("::")[0] not in file_set]
        tested = self._tests_of(changed)
        untested = [s for s in changed if not self._has_tests(s)]
        tickets = sorted(set(_TICKET_ID.findall(msgs)))
        # ADR-DEVKB-007: the pull requests that brought these commits in, and the issues those close
        prs: dict[int, None] = {}
        for sha in self._git("rev-list", "-n", "300", f"{base}..{head_rev}").split():
            c = self.idx.node("Commit", sha)
            for p in (self._prs_of_commit(c) if c is not None else []):
                prs[p] = None
        tickets = sorted(set(tickets) | {self._key(t) for p in prs for t in self.idx.targets("CLOSES", p)})
        pr_cov = self.pr_coverage([self._key(t) for p in prs for t in self.idx.targets("CLOSES", p) if self._link("CLOSES", p, t)[1]])
        docs: list[str] = []
        for tid in tickets:
            t = self.idx.node("Ticket", tid)
            if t is not None:
                docs += [self._key(x) for x in self.idx.sources("DOCUMENTS", t)] + [self._key(x) for x in self.idx.targets("IMPLEMENTS", t)]
        warnings = sorted({self.idx.props[w].get("rule", "?") for f in files for fi in [self.idx.node("File", f)] if fi is not None
                           for w in self.idx.targets("FLAGGED_BY", fi)})
        return {"rev": rev, "files": len(files), "changed_symbols": [self._key(s) for s in changed[:limit]],
                "n_changed_symbols": len(changed), "callers_outside": [self._key(c) for c in outside[:limit]],
                "n_callers_outside": len(outside), "tests": [{"f": f, "t": sorted(v)[:3]} for f, v in sorted(tested.items())[:8]],
                "untested": [self._key(s) for s in untested[:8]], "tickets": tickets[:6], "docs": sorted(set(docs))[:6],
                "warnings": warnings[:6], "owners": self._owners_of(sorted(files)),
                **({"drift": drifted[:6], "note": "these files changed after the commit; changed functions were read from the commit itself"} if drifted else {}),
                **({"unmapped": unmapped[:6]} if unmapped else {}),
                **({"pull_requests": [self._pr_row(p) for p in sorted(prs, key=self._key)[:6]]} if prs else {}),
                **({"coverage": pr_cov} if pr_cov is not None else {})}

    # ── developer tasks: one call for a whole kind of work (ODSF-310) ──────────────
    # A developer does not ask "who calls this?" and stop. They build a feature, change behaviour, fix a ticketed bug,
    # chase a root cause, refactor, review, learn an area. Each of those used to take four to six calls, and every call is
    # another model turn that re-reads the whole context. These return what the task needs at once.
    def _is_entry(self, i: int) -> bool:
        key = self._key(i)
        return key in self.idx.ep_by_owner or not self.idx.sources("CALLS", i) or key.endswith("::main")

    def _caller_count(self, i: int) -> int:
        """Production callers only: what depends on this code, not what checks it."""
        return sum(1 for c in set(self.idx.sources("CALLS", i)) if not is_test_path(self._key(c).split("::")[0]))

    def _test_caller_count(self, i: int) -> int:
        return sum(1 for c in set(self.idx.sources("CALLS", i)) if is_test_path(self._key(c).split("::")[0]))

    def _code_hits(self, query: str, limit: int = 8, under: str = "", tests: bool = False) -> list[tuple[float, int]]:
        toks = set(query_words(query))
        if not toks:
            return []
        n = max(1, self.idx.n_symbols)
        score: dict[int, float] = {}
        matched: dict[int, int] = {}
        for w in toks:
            hits = self.idx.code_inv.get(w, [])
            idf = math.log((n + 1) / (len(hits) + 1)) + 1
            for i, wt in hits:
                score[i] = score.get(i, 0.0) + idf * wt
                matched[i] = matched.get(i, 0) + 1
        ranked = []
        for i, s in score.items():
            path = self._key(i).split("::")[0]
            if (under and not path.startswith(under)) or (not tests and is_test_path(path)):
                continue
            ranked.append((s * (0.5 + 0.5 * matched[i] / len(toks)), i))
        ranked.sort(key=lambda r: (-r[0], -self._caller_count(r[1]), self._key(r[1])))
        return ranked[:limit]

    def _code_row(self, i: int) -> dict:
        p = self.idx.props[i]
        return {"k": self._key(i), "kind": p.get("kind"), "line": p.get("line_start"), "callers": self._caller_count(i),
                "doc": (p.get("docstring_summary") or "")[:64]}

    def find_code(self, query: str, limit: int = 8, under: str = "") -> dict:
        hits = self._code_hits(query, limit, under)
        return {"query": query, "n": len(hits), "code": [self._code_row(i) for _, i in hits]}

    def _recent_commits(self, files: list[str], limit: int = 6) -> list[dict]:
        found: dict[int, str] = {}
        for f in files:
            fi = self.idx.node("File", f)
            if fi is None:
                continue
            for c in self.idx.sources("TOUCHES", fi):
                if len(self.idx.targets("TOUCHES", c)) <= 40:  # a mass rename tells nothing about this file
                    found.setdefault(c, f)
        top = sorted(found, key=lambda c: (self.idx.props[c].get("date", ""), self._key(c)), reverse=True)[:limit]
        rows = [{"h": (self.idx.props[c].get("short_hash") or "")[:8], "d": self.idx.props[c].get("date"),
                 "s": (self.idx.props[c].get("subject") or "")[:72], "t": sorted(set(_TICKET_ID.findall(self.idx.props[c].get("subject") or ""))),
                 "f": found[c]} for c in top]
        for row, c in zip(rows, top):
            prs = self._prs_of_commit(c)
            if prs:
                row["pr"] = [self._key(p) for p in prs]
                closed = sorted({self._key(t) for p in prs for t in self.idx.targets("CLOSES", p)})
                if closed:
                    row["closes"] = closed[:4]
        return rows

    def history(self, files: list[str] | str, limit: int = 6) -> dict:
        files = [files] if isinstance(files, str) else list(files)
        return self._with_pr_coverage({"files": files, "commits": self._recent_commits(files, limit)})

    def _past_tickets(self, text: str, skip: str = "", bugs_only: bool = False, limit: int = 4) -> list[dict]:
        score: dict[int, float] = {}
        n = max(1, self.idx.type_count.get("Ticket", 1))
        for w in set(query_words(text)):
            hits = self.idx.ticket_inv.get(w, [])
            idf = math.log((n + 1) / (len(hits) + 1)) + 1
            for i in hits:
                score[i] = score.get(i, 0.0) + idf
        issues_rel = self.ctx.issues_dir.relative_to(self.root).as_posix() + "/" if self.ctx.issues_dir.is_relative_to(self.root) else "issues/"
        out = []
        for i in sorted(score, key=lambda i: (-score[i], self._key(i))):
            p = self.idx.props[i]
            if self._key(i) == skip or (bugs_only and p.get("ticket_type") != "BUG") or p.get("status") in ("OPEN", "BACKLOG", "WIP"):
                continue
            touched: dict[str, int] = {}
            for c in self.idx.sources("REFERENCES", i):
                for f in self.idx.targets("TOUCHES", c):
                    path = self._key(f)
                    if not path.startswith(issues_rel) and not path.endswith(".md"):
                        touched[path] = touched.get(path, 0) + 1
            out.append({"t": self._key(i), "title": (p.get("title") or "")[:70], "files": sorted(touched, key=lambda f: -touched[f])[:3]})
            if len(out) == limit:
                break
        return out

    def rca_trace(self, symptom: str, depth: int = 3, limit: int = 8) -> dict:
        toks = set(query_words(symptom))
        n = max(1, self.idx.type_count.get("ErrorSignature", 1))
        score: dict[int, float] = {}
        for w in toks:
            hits = self.idx.err_inv.get(w, [])
            idf = math.log((n + 1) / (len(hits) + 1)) + 1
            for e in hits:
                score[e] = score.get(e, 0.0) + idf
        sigs = [e for e in sorted(score, key=lambda e: (-score[e], self._key(e)))[:3] if score[e] > 0]
        # ODSF-313: a message quoted exactly names its raiser; the fuzzy runners-up are then noise, not candidates
        said = " ".join(symptom.lower().split())
        exact = [e for e in score if len(m := " ".join((self.idx.props[e].get("message_template") or "").lower().split())) >= 12
                 and m.replace("{}", "") and all(part.strip() in said for part in m.split("{}") if part.strip())]
        if exact:
            sigs = sorted(exact, key=self._key)[:3]
        raisers = sorted({s for e in sigs for verb in ("RAISES", "LOGS") for s in self.idx.sources(verb, e)}, key=self._key)
        how = "error message"
        if not raisers:
            hits = self._code_hits(symptom, 3)
            raisers, how = [i for _, i in hits], "code name (no error message matched)"
        if not raisers:
            return {"symptom": symptom, "error": "nothing in the graph matches this symptom; search the code directly"}
        levels = self._callers(set(raisers), max(1, min(int(depth), 4)))
        chain = [{"k": self._key(c), "d": d + 1, **({"entry": True} if self._is_entry(c) else {})}
                 for d, lv in enumerate(levels) for c in lv if not is_test_path(self._key(c).split("::")[0])]
        files = list(dict.fromkeys([self._key(s).split("::")[0] for s in raisers] + [c["k"].split("::")[0] for c in chain if c["d"] == 1]))[:8]
        tests = self._tests_of(raisers)
        flows = sorted({self._key(f) for s in raisers for f in self.idx.sources("STEP", s)})
        return {"symptom": symptom, "matched_by": how,
                "signatures": [{"msg": (self.idx.props[e].get("message_template") or self.idx.props[e].get("label") or "")[:90],
                                "kind": self.idx.props[e].get("kind")} for e in sigs] if how == "error message" else [],
                "raisers": [self._key(s) for s in raisers[:limit]], "chain": chain[:limit * 2],
                "entry_points": [c["k"] for c in chain if c.get("entry")][:limit], "flows": flows[:3],
                "recent": self._recent_commits(files, 6), "tests": [{"f": f, "t": sorted(v)[:3]} for f, v in sorted(tests.items())[:5]],
                "coverage": self._coverage(raisers[:3])}

    def bug_brief(self, ticket: str = "", text: str = "", limit: int = 6) -> dict:
        info: dict = {}
        if ticket:
            t, err = self._ticket(ticket)
            if err:
                return err
            p = self.idx.props[t]
            text = text or p.get("title") or ""
            info = {"ticket": ticket, "title": text[:110], "status": p.get("status"), "component": p.get("component"),
                    "owner_role": self._config().get("component_to_role", {}).get(p.get("component", ""), "")}
        if not text:
            return {"error": "give a ticket id or the symptom text"}
        rca = self.rca_trace(text, depth=2, limit=limit)
        suspects = rca.get("raisers") or []
        similar = self._past_tickets(text, skip=ticket, bugs_only=True)
        out = {**info, "matched_by": rca.get("matched_by", "none"), "suspects": suspects, "signatures": rca.get("signatures", []),
               "entry_points": rca.get("entry_points", []), "recent": rca.get("recent", []), "similar_bugs": similar,
               "tests": rca.get("tests", [])}
        if not suspects:
            out["note"] = "no suspect found by message or name; search the code directly"
        return out

    def feature_brief(self, goal: str, ticket: str = "", limit: int = 5) -> dict:
        hits = self._code_hits(goal, limit)
        top_files = list(dict.fromkeys(self._key(i).split("::")[0] for _, i in hits))[:3]
        out: dict = {"goal": goal[:110], "code": [self._code_row(i) for _, i in hits],
                     "docs": self.find_docs(goal, limit=4)["docs"], "similar_work": self._past_tickets(goal, skip=ticket),
                     "owners": self._owners_of(top_files)}
        if top_files:
            first = self.owner(top_files[0])
            out["boundary"] = {"path": top_files[0], "owner": first["owner"], "forbidden_for": first["forbidden_for"]}
            tests = self.tests_to_run(top_files, limit=5)
            out["tests"], out["run"] = tests["tests"], tests["run"]
        if ticket and self.idx.node("Ticket", ticket) is not None:
            ctx = self.sdlc_context(ticket)
            out["chain"] = {k: ctx[k] for k in ("epic", "spec", "requirement") if ctx.get(k)}
        return out

    def explain_area(self, path: str, limit: int = 8) -> dict:
        prefix = path.rstrip("/")
        files = [f for f in self.idx.sym_by_file if f == prefix or f.startswith(prefix + "/")]
        if not files:
            return {"error": f"no indexed source under {path}"}
        src = [f for f in files if not is_test_path(f)]
        syms = [s for f in src for s in self.idx.sym_by_file[f]]
        key_syms = sorted(syms, key=lambda s: (-self._caller_count(s), self._key(s)))[:limit]
        eps = sorted({self._key(e) for s in syms for e in self.idx.ep_by_owner.get(self._key(s), [])})
        topic = " ".join([prefix.replace("/", " ")] + [self._key(s).split("::")[-1] for s in key_syms[:3]])
        tests = self.tests_to_run(src[:12], limit=6)
        return {"path": path, "files": len(src), "symbols": len(syms),
                "key_symbols": [{"k": self._key(s), "prod_callers": self._caller_count(s), "test_callers": self._test_caller_count(s),
                                 "cx": self.idx.props[s].get("complexity")} for s in key_syms],
                "ranked_by": "prod_callers: distinct non-test functions that call it",
                "endpoints": eps[:6], "owners": self._owners_of(src[:30]),
                "docs": self.find_docs(topic, limit=3)["docs"], "tests": tests["tests"],
                "recent": self._recent_commits(src[:40], 4)}

    def refactor_scope(self, target: str, role: str = "", limit: int = 12) -> dict:
        syms = self._file_symbols(target)
        label = target
        if not syms:
            i, err = self._resolve(target)
            if err:
                return err
            syms, label = [i], self._key(i)
        own = set(syms)
        by_file: dict[str, int] = {}
        test_callers: dict[str, int] = {}
        for s in syms:
            for c in self.idx.sources("CALLS", s):
                if c in own:
                    continue
                f = self._key(c).split("::")[0]
                (test_callers if is_test_path(f) else by_file)[f] = (test_callers if is_test_path(f) else by_file).get(f, 0) + 1
        endpoints = sorted({self._key(e) for s in syms for e in self.idx.ep_by_owner.get(self._key(s), [])})
        flows = sorted({self._key(f) for s in syms for f in self.idx.sources("STEP", s)})
        files_to_touch = sorted(by_file, key=lambda f: -by_file[f])
        test_files = sorted(test_callers, key=lambda f: (-test_callers[f], f))
        blocked: list[str] = []
        if role:  # a test file a role may not edit blocks the change as much as a source file does
            dnt = self._role_table().get(role, {}).get("dnt", [])
            blocked = sorted(f for f in files_to_touch + test_files if any(f.startswith(p) for p in dnt))
        tests = self.tests_to_run(list(dict.fromkeys(list(syms and [self._key(syms[0]).split("::")[0]]) + files_to_touch)), limit=8)
        return {"target": label, "symbols": len(syms), "public": any(self.idx.props[s].get("is_public") for s in syms),
                "max_complexity": max((self.idx.props[s].get("complexity") or 0 for s in syms), default=0),
                "caller_files": [{"f": f, "n": by_file[f]} for f in files_to_touch[:limit]], "n_caller_files": len(by_file),
                "test_files": test_files[:30], "n_test_files": len(test_files), "endpoints": endpoints[:6], "flows": flows[:3],
                "blocked_files": blocked[:limit], "tests": tests["tests"], "run": tests["run"],
                "coverage": self._coverage(syms, set(by_file) | set(test_files)),
                **({"truncated": "caller_files or test_files is longer than shown; the n_ counts are complete"}
                   if len(by_file) > limit or len(test_files) > 30 else {})}

    # ── S9, S10: close and knowledge ───────────────────────────────────────
    def lineage(self, ticket: str) -> dict:
        t, err = self._ticket(ticket)
        if err:
            return err
        idx = self.idx
        out: dict = {"ticket": ticket, "status": idx.props[t].get("status")}
        for verb in ("CAUSED_BY", "REGRESSION_OF", "DUPLICATE_OF", "BLOCKS"):
            fwd = [self._key(x) for x in idx.targets(verb, t)]
            back = [self._key(x) for x in idx.sources(verb, t)]
            if fwd:
                out[verb.lower()] = fwd
            if back:
                out[f"{verb.lower()}_by"] = back
        prs = self._ticket_prs(t)
        # a pull request that closes the ticket brings its commits into the ticket's history (ADR-DEVKB-007)
        via_prs = {c for p in prs for c in idx.targets("MERGES", p)}
        commits = sorted(set(idx.sources("REFERENCES", t)) | via_prs, key=lambda c: idx.props[c].get("date", ""))
        out["commits"] = len(commits)
        if commits:
            out["first"], out["last"] = idx.props[commits[0]].get("short_hash"), idx.props[commits[-1]].get("short_hash")
        out["spec"] = [self._key(x) for x in idx.targets("IMPLEMENTS", t)]
        out["work_package"] = [self._key(x) for x in idx.targets("PART_OF", t)]
        if prs:
            out["pull_requests"] = [self._pr_row(x, "CLOSES", t) for x in prs]
        if self._is_hosted(ticket):
            epic = [self._key(x) for x in idx.targets("CHILD_OF", t)]
            kids = [self._key(x) for x in sorted(set(idx.sources("CHILD_OF", t)), key=self._key)]
            if epic:
                out["epic"] = epic
            if kids:
                out["sub_issues"] = kids
        if prs or self._is_hosted(ticket):
            self._with_pr_coverage(out, self._pr_unverified(t, prs))
        return out

    # ── configuration and repositories (ADR-SDP-DEVKB-005, ODSF-312) ────────────
    def _repo_of(self, key: str) -> str:
        head = key.split("/", 1)[0]
        return head.split(":", 1)[0] if ":" in head and head.split(":", 1)[0].isupper() else self.idx.code

    def _readers(self, ck: int) -> list[int]:
        return sorted(set(self.idx.sources("READS", ck)), key=self._key)

    def config(self, query: str = "", limit: int = 12) -> dict:
        """A setting or a service: who reads the setting, which files declare it and which services those files
        deploy, in which repositories; or, for a service, its file, image, ports and settings. No query: an overview
        with the settings that are read but declared nowhere and declared but read nowhere."""
        idx, q = self.idx, query.strip()
        keys = [i for (t, _k), i in idx.by_key.items() if t == "ConfigKey"]
        comps = [i for (t, _k), i in idx.by_key.items() if t == "Component"]
        if not q:
            read = [i for i in keys if idx.sources("READS", i)]
            declared = {i for i in keys if idx.sources("DECLARES", i)}
            kinds: dict[str, int] = {}
            for c in comps:
                kinds[idx.props[c].get("kind") or "discovery"] = kinds.get(idx.props[c].get("kind") or "discovery", 0) + 1
            top = sorted(read, key=lambda i: (-len(set(idx.sources("READS", i))), self._key(i)))[:limit]
            env = [i for i in keys if idx.props[i].get("kind") == "env"]
            return {"settings": len(keys), "read_in_code": len(read), "components": kinds,
                    "repositories": sorted(self._key(i) for (t, _k), i in idx.by_key.items() if t == "Repository"),
                    "most_read": [{"k": self._key(i), "readers": len(set(idx.sources("READS", i)))} for i in top],
                    "read_not_declared": sorted(self._key(i) for i in env if i not in declared and idx.sources("READS", i))[:limit],
                    "declared_not_read": sorted(self._key(i) for i in env if i in declared and not idx.sources("READS", i))[:limit]}
        ck = idx.node("ConfigKey", q) or idx.node("ConfigKey", q.upper())
        if ck is not None:
            readers = self._readers(ck)
            files = sorted({self._key(f) for f in idx.sources("DECLARES", ck)})
            deployed = sorted({self._key(c) for f in idx.sources("DECLARES", ck) for c in idx.targets("DEPLOYS", f)})
            return {"setting": self._key(ck), "kind": idx.props[ck].get("kind"), "n_readers": len(readers),
                    "read_by": [self._key(r) for r in readers[:limit]], "declared_in": files[:limit], "deployed_by": deployed[:limit],
                    "repositories": sorted({self._repo_of(self._key(r)) for r in readers} | {self._repo_of(f) for f in files}),
                    **({"note": "read in code but declared in no example env file, compose file, unit or Dockerfile"}
                       if readers and not files and idx.props[ck].get("kind") == "env" else {})}
        comp = idx.node("Component", q) or next((c for c in comps if idx.props[c].get("label") == q), None)
        if comp is not None:
            p = idx.props[comp]
            files = [self._key(f) for f in idx.sources("DEPLOYS", comp)]
            settings = sorted({self._key(k) for f in idx.sources("DEPLOYS", comp) for k in idx.targets("DECLARES", f)})
            return {"component": self._key(comp), **{k: p[k] for k in ("kind", "file", "image", "ports", "exec") if p.get(k)},
                    "defined_in": files, "settings": [{"k": s, "readers": len(self._readers(idx.node("ConfigKey", s)))} for s in settings[:limit]]}
        ql = q.lower()
        hits = sorted((i for i in keys if ql in self._key(i).lower()), key=lambda i: (-len(set(idx.sources("READS", i))), self._key(i)))
        chits = sorted((c for c in comps if ql in self._key(c).lower()), key=self._key)
        if not hits and not chits:
            return {"error": f"no setting or component matches {query!r}; call config with no query for an overview"}
        return {"query": q, "settings": [{"k": self._key(i), "readers": len(set(idx.sources("READS", i)))} for i in hits[:limit]],
                "components": [{"k": self._key(c), "kind": idx.props[c].get("kind")} for c in chits[:limit]]}

    # ── documents and roles (ODSF-311) ────────────────────────────────────────────
    # Writing a design, a specification or a test specification, reviewing one, and starting a session as a particular
    # role are all work an agent does before it writes code. They need facts from the graph (what exists, who owns it,
    # what is untested, what changed since a document was written) and a shape (the sections the document should have).
    def _flow_of(self, entry: str) -> int | None:
        idx = self.idx
        if ("Flow", entry) in idx.by_key:
            return idx.by_key[("Flow", entry)]
        sym = None
        ep = idx.node("Endpoint", entry)
        if ep is not None and idx.props[ep].get("owner_symbol"):
            sym = idx.node("Symbol", idx.props[ep]["owner_symbol"])
        if sym is None:
            sym, err = self._resolve(entry)
            if err:
                return None
        for kind in ("endpoint", "daemon_entry", "ui_handler"):
            flow = idx.node("Flow", f"flow:{kind}:{self._key(sym)}")
            if flow is not None:
                return flow
        flows = idx.sources("STEP", sym)
        return min(flows, key=lambda f: len(idx.flow_steps.get(f, []))) if flows else None

    def flow_sequence(self, entry: str, limit: int = 12) -> dict:
        """The recorded call order from an entry point, as numbered messages and as Mermaid text for a sequence diagram."""
        flow = self._flow_of(entry)
        if flow is None:
            return {"error": f"no recorded flow for {entry}; flows are recorded from endpoints, daemon entries and UI handlers"}
        steps = [s for _, s in self.idx.flow_steps.get(flow, []) if self.idx.types[s] == "Symbol"]
        pos = {s: n for n, s in enumerate(steps)}
        messages = [(a, b) for a in steps for b in sorted(set(self.idx.targets("CALLS", a)), key=lambda x: pos.get(x, 1 << 30))
                    if b in pos and b != a]
        shown = messages[:limit]
        files = list(dict.fromkeys(self._key(s).split("::")[0] for pair in shown for s in pair))
        alias = {f: f"p{n}" for n, f in enumerate(files)}
        lines = ["sequenceDiagram"] + [f"  participant {alias[f]} as {f}" for f in files]
        for a, b in shown:
            lines.append(f"  {alias[self._key(a).split('::')[0]]}->>{alias[self._key(b).split('::')[0]]}: {self._key(b).split('::')[-1].split('.')[-1]}")
        return {"flow": self._key(flow), "kind": self.idx.props[flow].get("touch_point_kind"), "n_steps": len(steps),
                "n_messages": len(messages), "participants": files,
                "messages": [f"{self._key(a)} -> {self._key(b)}" for a, b in shown], "mermaid": "\n".join(lines),
                **({"truncated": True} if len(messages) > limit else {})}

    def _public_symbols(self, area: str) -> list[int]:
        prefix = area.rstrip("/")
        files = [f for f in self.idx.sym_by_file if (f == prefix or f.startswith(prefix + "/")) and not is_test_path(f)]
        syms = [s for f in files for s in self.idx.sym_by_file[f]]
        if not syms:
            i, err = self._resolve(area)
            if not err:
                syms = [i]
        return [s for s in syms if self.idx.props[s].get("kind") in ("function", "method", "class")
                and not self._key(s).split("::")[-1].split(".")[-1].startswith("_")]

    def test_items(self, area: str, limit: int = 10) -> dict:
        """Candidate test items for a path, directory or function, derived from what the code does: each error it
        raises (a negative test), each endpoint it serves (a contract test) and each untested branchy function."""
        public = self._public_symbols(area)
        if not public and "/" not in area and "." not in area:  # plain words, not a path: search for the code
            public = [i for _, i in self._code_hits(area, 6)]
        if not public:
            return {"error": f"no public code under {area} in the graph built at {self.idx.git_head[:8]}"}
        items: list[dict] = []
        untested = [s for s in public if not self._has_tests(s)]
        for s in public:
            name, covered = self._key(s).split("::")[-1], self._has_tests(s)
            for e in self.idx.targets("RAISES", s):
                p = self.idx.props[e]
                items.append({"item": f"{name} raises {p.get('label')} when: {(p.get('message_template') or '')[:60]}",
                              "kind": "negative", "target": self._key(s), "covered": covered})
            for ep in self.idx.ep_by_owner.get(self._key(s), []):
                items.append({"item": f"{self._key(ep)}: valid input, invalid input, and who may call it", "kind": "contract",
                              "target": self._key(s), "covered": covered})
        for s in untested:
            cx = self.idx.props[s].get("complexity") or 0
            if cx >= 3:
                items.append({"item": f"{self._key(s).split('::')[-1]}: every branch (complexity {cx})", "kind": "branch",
                              "target": self._key(s), "covered": False})
        order = {"negative": 0, "contract": 1, "branch": 2}
        items.sort(key=lambda it: (it["covered"], order[it["kind"]], it["target"]))
        files = list(dict.fromkeys(self._key(s).split("::")[0] for s in public))
        tests = self.tests_to_run(files[:12], limit=6)
        cases = self._register_cases(set(tests["tests"]))
        return {"area": area, "public": len(public), "untested": len(untested), "n_items": len(items), "items": items[:limit],
                "existing_tests": tests["tests"], "run": tests["run"], **({"register_cases": cases} if cases else {})}

    def _register_cases(self, test_files: set[str]) -> list[str]:
        """Ids of x03 test-case register cases bound to any of these test files, when the project keeps a register."""
        try:
            cfg = json.loads((self.root / "st.config.json").read_text())
            register = json.loads((self.root / cfg["register"]).read_text())
        except (OSError, ValueError, KeyError):
            return []
        cases = register.get("cases") or {}
        return [cid for cid, c in cases.items() if str((c.get("binding") or {}).get("node", "")).split("::")[0] in test_files][:6]

    def _next_spec_id(self) -> str | None:
        found: dict[str, list[int]] = {}
        for sid in self.idx.spec_by_id:
            m = re.match(r"^spec-([a-z0-9]+)-(\d+)$", sid)
            if m:
                found.setdefault(m.group(1).upper(), []).append(int(m.group(2)))
        if not found:
            return None
        code = max(found, key=lambda c: len(found[c]))
        return f"SPEC-{code}-{max(found[code]) + 1:03d}"

    def design_brief(self, kind: str, topic: str, limit: int = 5) -> dict:
        """What to ground a document in, and the shape it should have: the sections for this kind of document, the facts
        from the graph that fill them, the existing documents to align with, and the next free specification id."""
        k = KIND_ALIASES.get(kind.lower().strip(), kind.lower().strip())
        if k not in TEMPLATES:
            return {"error": f"kind must be one of {sorted(TEMPLATES)}"}
        hits = self._code_hits(topic, limit)
        files = list(dict.fromkeys(self._key(i).split("::")[0] for _, i in hits))[:4]
        docs = self.find_docs(topic, limit=3)["docs"]
        for d in docs:
            i = self.idx.node("Spec", d["p"])
            d["heads"] = [h[:48] for h in self.idx.spec_heads.get(i, [])[:8]] if i is not None else []
        syms = [i for _, i in hits]
        endpoints = sorted({self._key(e) for s in syms for e in self.idx.ep_by_owner.get(self._key(s), [])})
        errors = [f"{self.idx.props[e].get('label')}: {(self.idx.props[e].get('message_template') or '')[:60]}"
                  for s in syms for e in self.idx.targets("RAISES", s)][:6]
        facts: dict = {"code": [self._code_row(i) for i in syms]}
        if k in ("functional", "detailed"):
            facts["interfaces"], facts["errors"] = endpoints[:6], errors
        if k == "detailed":
            facts["symbols"] = [{"k": self._key(s), "line": self.idx.props[s].get("line_start"), "cx": self.idx.props[s].get("complexity")} for s in syms]
        if k == "architecture":
            area: dict[str, set[str]] = {}
            for f in files + [self._key(c).split("::")[0] for s in syms for c in self.idx.sources("CALLS", s)][:12]:
                area.setdefault("/".join(f.split("/")[:2]), set()).add(f)
            facts["components"] = [{"area": a, "files": len(fs)} for a, fs in sorted(area.items())][:6]
            facts["interfaces"] = endpoints[:6]
            facts["decisions"] = self.find_docs(topic, kinds=["adr"], limit=3)["docs"]
        if k == "sequence" and syms:
            flow = self._flow_of(self._key(syms[0])) or next((self._flow_of(self._key(c)) for lv in self._callers({syms[0]}, 3) for c in lv
                                                              if self._flow_of(self._key(c)) is not None), None)
            if flow is not None:
                seq = self.flow_sequence(self._key(flow), limit=8)
                facts["flow"] = {k2: seq[k2] for k2 in ("flow", "participants", "messages", "mermaid") if k2 in seq}
        if k == "test_spec":
            ti = self.test_items(topic, limit=8)
            facts["test_items"] = {k2: ti[k2] for k2 in ("public", "untested", "items", "run") if k2 in ti}
        return {"kind": k, "topic": topic[:80], "outline": TEMPLATES[k], "front_matter": FRONT_MATTER,
                "next_spec_id": self._next_spec_id(), "docs": docs, "facts": facts, "similar_work": self._past_tickets(topic, limit=3),
                "owners": self._owners_of(files)}

    def review_doc(self, path: str, kind: str = "") -> dict:
        """Review a design, specification or test-specification document against the repository: references that do not
        exist, code it describes that changed after it was written, important code it never mentions, sections it lacks."""
        doc = self.root / path
        if not doc.is_file():
            return {"error": f"no document at {path}"}
        text = doc.read_text(errors="replace")[:200_000]
        k = KIND_ALIASES.get(kind.lower().strip(), kind.lower().strip()) if kind else ""
        refs = {m.lstrip("/") for m in re.findall(r"[\w./-]+\.(?:py|tsx|ts|jsonl|json|js|md|sh|toml|yaml|yml)(?![\w-])", text)
                if ("/" in m or (self.root / m).exists()) and "..." not in m}
        # A path whose top directory is not in this repository names another repository or an example; only a path
        # into a directory that exists here and a file that does not is a broken reference.
        missing = [p for p in refs if not (self.root / p).exists()]
        broken_paths = sorted(p for p in missing if (self.root / p.split("/")[0]).is_dir())
        elsewhere = len(missing) - len(broken_paths)
        ticket_re = re.compile(r"\b" + re.escape(self.ctx.ticket_prefix) + r"-\d+\b")
        broken_tickets = sorted({t for t in ticket_re.findall(text) if self.idx.node("Ticket", t) is None})
        # Only a name written as code that runs counts: `name()` or `path::name`. A bare `TestCase` or `first_seen` in a
        # design is as often a type, a field or a word as a function, and flagging those buries the real misses.
        called = set(re.findall(r"`([A-Za-z_][\w.]*)\([^`]*\)`", text)) | set(re.findall(r"`[\w-]*[./][\w./-]*::([\w.]+)`", text))
        unknown_symbols = sorted(n for n in called if not self.idx.short.get(n.split(".")[-1]) and n.split(".")[0] not in LIBRARY_NAMES)
        spec_ids = {s for s in re.findall(r"\b(?:SPEC|ADR)-[A-Z0-9-]+\b", text)}
        known_ids = {k.upper() for k in self.idx.spec_by_id} | {self._key(i).upper() for i in self.idx.spec_terms}
        broken_ids = sorted(s for s in spec_ids if s.upper() not in known_ids and not any(s.upper() in key for key in known_ids)
                            and not re.search(r"-(?:N+|X+)$", s))  # ADR-...-NNN is a placeholder, not a reference
        existing = [p for p in refs if (self.root / p).exists()]
        stamp = (path, doc.stat().st_mtime_ns, self.idx.git_head)
        if stamp not in self._written:
            self._written[stamp] = self._git("log", "-1", "--format=%cs", "--", path).strip()
        written = self._written[stamp]
        drift = []
        if written:
            for f in existing:
                fi = self.idx.node("File", f)
                if fi is None:
                    continue
                newer = [c for c in self.idx.sources("TOUCHES", fi) if (self.idx.props[c].get("date") or "") > written
                         and len(self.idx.targets("TOUCHES", c)) <= 40]
                if newer:
                    drift.append({"f": f, "newer_commits": len(newer)})
        drift.sort(key=lambda d: -d["newer_commits"])
        unmentioned: list[str] = []
        code_files = [f for f in existing if f in self.idx.sym_by_file and not is_test_path(f)]
        if code_files:
            common = max({"/".join(f.split("/")[:-1]) or f for f in code_files}, key=lambda d: sum(1 for f in code_files if f.startswith(d)))
            area = self.explain_area(common, limit=8) if common else {}
            unmentioned = [s["k"] for s in area.get("key_symbols", []) if not s["k"].split("::")[-1].split(".")[-1].startswith("_")
                           and s["k"].split("::")[-1].split(".")[-1] not in text][:5]
        heads = [ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")][:40]
        missing = []
        if k in TEMPLATES:
            head_words = {w for h in heads for w in words(h)}
            missing = [sec for sec in TEMPLATES[k] if not ({w for w in words(sec) if w not in STOP} & head_words)]
        items_gap: list[str] = []
        if k == "test_spec" and code_files:
            ti = self.test_items(common, limit=40)
            items_gap = [it["item"][:70] for it in ti.get("items", []) if not it["covered"] and it["target"].split("::")[-1].split(".")[-1] not in text][:5]
        return {"path": path, "kind": k or "any", "words": len(text.split()), "headings": len(heads),
                "front_matter": text.startswith("---"), "missing_sections": missing,
                "broken": {"paths": broken_paths[:8], "symbols": unknown_symbols[:8], "tickets": broken_tickets[:8], "doc_ids": broken_ids[:6]},
                "outside_repo_paths": elsewhere,
                "drift": drift[:6], "written": written, "unmentioned": unmentioned, "untested_items_not_in_doc": items_gap,
                "owners": self._owners_of(existing[:20])}

    def _role_info(self, code: str) -> tuple[str, dict]:
        table = self._role_table()
        match = next((c for c in table if c.lower() == code.lower()), "")
        return match, table.get(match, {})

    def role_brief(self, role: str, limit: int = 6) -> dict:
        """Everything a role needs to start a session, from the graph and the role profile: territory, work waiting,
        the code it owns and how to test it, the documents to read, and what is specific to the role."""
        code, spec = self._role_info(role)
        if not code:
            return {"error": f"unknown role {role}; known: {', '.join(sorted(self._role_table())) or 'none declared'}"}
        idx = self.idx
        profile_file = self._profiles().get(code, "")
        profile: dict = {"file": f"sdp/process/roles/{profile_file}"} if profile_file else {}
        try:
            body = (self._roles_dir() / profile_file).read_text()
            for key, label in (("Mission", "mission"), ("Decides", "decides"), ("Does NOT decide", "not_decide")):
                m = re.search(r"\*\*" + key + r"\*\*:\s*(.+(?:\n(?![ \t]*\n|\*\*|#|- ).+)*)", body)
                if m:  # a profile field may wrap over several lines
                    profile[label] = clip(" ".join(m.group(1).split()), 240)
        except OSError:
            pass
        mine, counts = [], {}
        prio = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        for (typ, key), i in idx.by_key.items():
            if typ != "Ticket" or idx.props[i].get("assignee") != code:
                continue
            st = idx.props[i].get("status") or "?"
            counts[st] = counts.get(st, 0) + 1
            if st in ("OPEN", "WIP", "REVIEW", "BACKLOG"):
                mine.append(i)
        mine.sort(key=lambda i: (prio.get(idx.props[i].get("priority"), 9), self._key(i)))
        own = spec.get("own", [])
        files = [f for f in idx.sym_by_file if any(f.startswith(p) for p in own) and not is_test_path(f)]
        syms = [s for f in files for s in idx.sym_by_file[f]]
        key_syms = sorted(syms, key=lambda s: (-self._caller_count(s), self._key(s)))[:limit]
        eps = sorted({self._key(e) for s in syms for e in idx.ep_by_owner.get(self._key(s), [])})
        tests = self.tests_to_run(files[:40], limit=5) if files else {"tests": [], "run": ""}
        # What the role decides finds its documents better than its paths do (sdp/devsecops names the devkb ADRs).
        topic = (profile.get("decides", "") + " " + " ".join(p.strip("/").replace("/", " ") for p in own[:2])).strip()
        out: dict = {"role": code, "profile": profile, "territory": {"own": own, "forbidden": spec.get("dnt", [])},
                     "work": {"counts": counts, "open": [{"t": self._key(i), "p": idx.props[i].get("priority"), "s": idx.props[i].get("status"),
                                                           "title": clip(idx.props[i].get("title") or "", 100)} for i in mine[:limit]]},
                     "area": {"files": len(files), "symbols": len(syms),
                              "key_symbols": [{"k": self._key(s), "prod_callers": self._caller_count(s)} for s in key_syms],
                              "endpoints": eps[:limit], "tests": tests["tests"], "run": tests["run"]},
                     "docs": self.find_docs(topic, limit=3)["docs"] if topic else []}
        c = code.upper()
        extras: dict = {}
        if c in ("QA", "TEST", "TESTER", "QAE", "SET"):
            ti = self.test_items(own[0], limit=6) if own and any(f.startswith(own[0]) for f in idx.sym_by_file) else {}
            extras["untested"] = ti.get("untested")
            extras["test_items"] = [it["item"][:80] for it in ti.get("items", []) if not it["covered"]][:5]
        if c == "TL":
            review = [i for (typ, _k), i in idx.by_key.items() if typ == "Ticket" and idx.props[i].get("status") == "REVIEW"]
            drafts = [self._key(i) for (typ, _k), i in idx.by_key.items() if typ == "Spec" and idx.props[i].get("status") in ("draft", "proposed")]
            merges = sorted((i for (typ, _k), i in idx.by_key.items() if typ == "Commit" and (idx.props[i].get("subject") or "").startswith("Merge")),
                            key=lambda i: idx.props[i].get("date", ""), reverse=True)[:3]
            extras = {"in_review": len(review), "review_queue": [self._key(i) for i in review[:limit]], "draft_specs": len(drafts),
                      "draft_list": drafts[:4], "recent_merges": [(idx.props[i].get("subject") or "")[:70] for i in merges]}
        if c in ("OPS", "DEVOPS", "SRE"):
            daemons = sorted((i for (typ, _k), i in idx.by_key.items() if typ == "Flow" and idx.props[i].get("touch_point_kind") == "daemon_entry"),
                             key=lambda i: -(idx.props[i].get("step_count") or 0))[:5]
            warn = {}
            for (typ, _k), i in idx.by_key.items():
                if typ == "Warning":
                    warn[idx.props[i].get("severity") or "?"] = warn.get(idx.props[i].get("severity") or "?", 0) + 1
            cfg = self.config(limit=6)  # ODSF-312: what runs, and settings nothing declares
            extras = {"daemon_entry_flows": [self._key(i) for i in daemons], "warnings_by_severity": warn,
                      "components": cfg["components"], "settings_read_not_declared": cfg["read_not_declared"],
                      "gates": sorted(k for (typ, k) in idx.by_key if typ == "File" and "quality-gates/gate-" in k)[:8]}
        if c in ("DSA", "TA", "ARCH", "ARCHITECT"):
            adrs = sorted(((idx.props[i].get("status"), self._key(i)) for (typ, _k), i in idx.by_key.items()
                           if typ == "Spec" and idx.props[i].get("doc_type") == "adr"), reverse=True)[:5]
            extras = {"adrs": [f"{s or '?'}: {p}" for s, p in adrs], "subsystems": sorted({k for (typ, k) in idx.by_key if typ in ("Subsystem", "Component")})[:8]}
        if c in ("BA", "PO"):
            stories = {}
            for (typ, _k), i in idx.by_key.items():
                if typ == "Ticket" and idx.props[i].get("ticket_type") in ("EPIC", "STORY"):
                    key = f"{idx.props[i].get('ticket_type')}/{idx.props[i].get('status')}"
                    stories[key] = stories.get(key, 0) + 1
            extras = {"epics_and_stories": stories, "next_spec_id": self._next_spec_id()}
        if extras:
            out["extras"] = extras
        out["ask"] = ROLE_SKILLS.get(c, ROLE_SKILLS["dev"])
        return out


TOOL_ARGS = {
    "graph-status": ("graph_status", []), "symbol": ("symbol", ["name"]), "callers": ("callers", ["symbol"]),
    "callees": ("callees", ["symbol"]), "tests-for": ("tests_for", ["ref"]), "tests-to-run": ("tests_to_run", ["files"]),
    "impact": ("impact", ["files"]), "owner": ("owner", ["path"]), "sdlc-context": ("sdlc_context", ["ticket"]),
    "trace": ("trace", ["ticket"]), "find-docs": ("find_docs", ["topic"]), "review-pack": ("review_pack", ["rev"]),
    "lineage": ("lineage", ["ticket"]), "pull-request": ("pull_request", ["pr"]),
    "find-code": ("find_code", ["query"]), "history": ("history", ["files"]), "feature-brief": ("feature_brief", ["goal"]),
    "bug-brief": ("bug_brief", ["ticket"]), "rca-trace": ("rca_trace", ["symptom"]), "refactor-scope": ("refactor_scope", ["target"]),
    "explain-area": ("explain_area", ["path"]),
    "flow-sequence": ("flow_sequence", ["entry"]), "test-items": ("test_items", ["area"]),
    "design-brief": ("design_brief", ["kind", "topic"]), "review-doc": ("review_doc", ["path", "kind"]),
    "role-brief": ("role_brief", ["role"]),
    "config": ("config", ["query"]),
}


TEXT_TOOLS = frozenset({"find-code", "feature-brief", "rca-trace", "find-docs"})


def _coerce(name: str, value: str):
    if name in ("files",):
        return [v for v in value.split(",") if v]
    return int(value) if value.isdigit() else value


# Document shapes for design_brief and review_doc (ODSF-311). Short on purpose: a section name that says what goes in it.
TEMPLATES = {
    "functional": ["Purpose and users", "Scope and non-goals", "Functional requirements, numbered and testable",
                   "Interfaces: commands, endpoints, data in and out", "Business rules and error handling",
                   "Acceptance criteria", "Traceability to requirement and tickets"],
    "architecture": ["Context and constraints", "Components and responsibilities", "Interfaces between components",
                     "Data and state", "Key decisions with ADR links", "Quality attributes", "Risks and open questions"],
    "detailed": ["Modules and files", "Data structures", "Algorithms and rules", "Error handling",
                 "Interfaces and signatures", "Test hooks", "Migration and compatibility"],
    "sequence": ["Participants", "Main flow as numbered messages", "Alternative and error flows", "Preconditions and postconditions"],
    "test_spec": ["Scope and objectives", "Test items", "Test cases with steps and expected results", "Test data and fixtures",
                  "Entry and exit criteria", "Traceability to requirements"],
}
KIND_ALIASES = {"function": "functional", "functional_design": "functional", "design": "detailed", "detail": "detailed",
                "detailed_design": "detailed", "arch": "architecture", "architecture_design": "architecture",
                "test": "test_spec", "testspec": "test_spec", "test-spec": "test_spec", "test_specification": "test_spec",
                "seq": "sequence", "sequence_diagram": "sequence"}
def clip(text: str, n: int) -> str:
    """Shorten at a sentence end if one is near the limit, else at a word, never mid-word."""
    if len(text) <= n:
        return text
    cut = text[:n]
    end = cut.rfind(". ")
    if end >= n * 0.5:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + " …" if " " in cut else cut + "…"


# Library and builtin names a design quotes as calls; they are not this repository's code, so never a broken reference.
LIBRARY_NAMES = frozenset("sha256 sha1 md5 hashlib len str int float dict list set tuple print open sorted json os re sys "
                          "subprocess pathlib Path time datetime uuid isinstance getattr fetch require useEffect useState".split())
FRONT_MATTER = ["id", "title", "type", "status", "created", "updated", "owner", "source", "tickets"]
# Which developer-task skills a role reaches for first; role_brief names them so a session starts with the right ones.
ROLE_SKILLS = {
    "dev": ["devkb-feature", "devkb-enhance", "devkb-bugfix", "devkb-refactor"],
    "QA": ["devkb-testspec", "devkb-design-review", "devkb-review", "devkb-rca"],
    "TL": ["devkb-review", "devkb-design-review", "devkb-onboard", "devkb-spec"],
    "OPS": ["devkb-rca", "devkb-onboard", "devkb-review"],
    "DSA": ["devkb-spec", "devkb-design-review", "devkb-onboard"],
    "BA": ["devkb-spec", "devkb-design-review"], "PO": ["devkb-spec", "devkb-design-review"],
    "DE": ["devkb-feature", "devkb-rca", "devkb-testspec"], "MLE": ["devkb-feature", "devkb-rca", "devkb-testspec"],
    "KC": ["devkb-onboard", "devkb-design-review"], "CM": ["devkb-review", "devkb-onboard"],
}
ROLE_SKILLS["TA"] = ROLE_SKILLS["ARCH"] = ROLE_SKILLS["DSA"]
ROLE_SKILLS["TEST"] = ROLE_SKILLS["TESTER"] = ROLE_SKILLS["QA"]
ROLE_SKILLS["DEVOPS"] = ROLE_SKILLS["SRE"] = ROLE_SKILLS["OPS"]

LATENCY_TARGET_MS = 50
REPLY_TARGET_BYTES = 4096


def bench_api(api: ProcessAPI, reps: int = 25) -> dict:
    """Time every tool, warm, on arguments that can succeed. An error reply is tiny and fast and would flatter
    the numbers, so a tool that has no valid sample is listed under `skipped`, never counted as fast (ODSF-309:
    the first version timed six of the eleven tools and quoted that as the API's latency)."""
    idx = api.idx
    unique = [v[0] for v in idx.short.values() if len(v) == 1 and idx.sources("CALLS", v[0])]
    sym = idx.keys[max(unique, key=lambda s: len(idx.sources("CALLS", s)))] if unique else None
    files = [f for f, ss in idx.sym_by_file.items() if any(idx.sources("CALLS", s) for s in ss)][:3]
    tickets = [(k, i) for (t, k), i in idx.by_key.items() if t == "Ticket"]
    busy = max(tickets, key=lambda p: len(idx.sources("REFERENCES", p[1])))[0] if tickets else None
    story = next((k for k, i in tickets if idx.props[i].get("ticket_type") == "STORY"), None)
    head = api._git("log", "-1", "--format=%h", "--no-merges", "--", "*.py").strip()
    msg = next((idx.props[i].get("message_template") for (typ, _k), i in idx.by_key.items()
                if typ == "ErrorSignature" and len(words(idx.props[i].get("message_template") or "")) >= 3), None)
    flows = sorted((i for (typ, _k), i in idx.by_key.items() if typ == "Flow"), key=lambda i: -len(idx.flow_steps.get(i, [])))
    flow = idx.keys[flows[0]] if flows else None
    doc = next((idx.keys[i] for i in sorted(idx.spec_terms) if (api.root / idx.keys[i]).is_file()), None)
    role = next(iter(sorted(api._role_table())), None)
    setting = next((idx.keys[i] for (typ, _k), i in sorted(idx.by_key.items()) if typ == "ConfigKey" and idx.sources("READS", i)), None)
    plan: list[tuple[str, dict | None, str]] = [
        ("graph_status", {}, ""), ("symbol", {"name": sym.split("::")[-1]} if sym else None, "no symbol with a caller"),
        ("callers", {"symbol": sym, "depth": 2} if sym else None, "no symbol with a caller"),
        ("callees", {"symbol": sym} if sym else None, "no symbol with a caller"),
        ("tests_for", {"ref": files[0]} if files else None, "no file with callers"),
        ("tests_to_run", {"files": files} if files else None, "no file with callers"),
        ("impact", {"files": files, "depth": 3} if files else None, "no file with callers"),
        ("owner", {"path": files[0]} if files else None, "no file with callers"),
        ("sdlc_context", {"ticket": busy} if busy else None, "no tickets"),
        ("lineage", {"ticket": busy} if busy else None, "no tickets"),
        ("trace", {"ticket": story} if story else None, "no STORY ticket"),
        ("find_docs", {"topic": "quality gate readiness specification"} if idx.spec_terms else None, "no specs"),
        ("review_pack", {"rev": head} if head else None, "no python commit"),
        ("find_code", {"query": " ".join(words(sym.split("::")[-1]))} if sym else None, "no symbol with a caller"),
        ("history", {"files": files[:2]} if files else None, "no file with callers"),
        ("feature_brief", {"goal": " ".join(words(sym.split("::")[-1])) + " handling"} if sym else None, "no symbol with a caller"),
        ("bug_brief", {"ticket": busy} if busy else None, "no tickets"),
        ("rca_trace", {"symptom": msg} if msg else None, "no error signature"),
        ("refactor_scope", {"target": sym} if sym else None, "no symbol with a caller"),
        ("explain_area", {"path": files[0].rsplit("/", 1)[0] if "/" in files[0] else files[0]} if files else None, "no file with callers"),
        ("flow_sequence", {"entry": flow} if flow else None, "no recorded flow"),
        ("test_items", {"area": files[0]} if files else None, "no file with callers"),
        ("design_brief", {"kind": "detailed", "topic": " ".join(words(sym.split("::")[-1]))} if sym else None, "no symbol with a caller"),
        ("review_doc", {"path": doc, "kind": "detailed"} if doc else None, "no spec document on disk"),
        ("role_brief", {"role": role} if role else None, "no declared role"),
        ("config", {"query": setting} if setting else None, "no setting read in code")]
    per_tool: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    for tool, kw, why in plan:
        if kw is None:
            skipped[tool] = why
            continue
        t0 = time.perf_counter()
        first = api.call(tool, **kw)
        first_ms = (time.perf_counter() - t0) * 1000
        if "error" in first:
            skipped[tool] = "error: " + str(first["error"])[:60]
            continue
        samples = []
        for _ in range(8 if tool in ("trace", "review_pack") else reps):
            t0 = time.perf_counter()
            r = api.call(tool, **kw)
            samples.append((time.perf_counter() - t0) * 1000)
        samples.sort()
        per_tool[tool] = {"first_ms": round(first_ms, 2), "p50_ms": round(statistics.median(samples), 2),
                          "p95_ms": round(samples[max(0, int(len(samples) * 0.95) - 1)], 2),
                          "bytes": len(json.dumps(r, separators=(",", ":")))}
    worst = max(per_tool, key=lambda k: per_tool[k]["p95_ms"]) if per_tool else ""
    return {"tools": len(per_tool), "per_tool": per_tool, "skipped": skipped, "slowest": worst,
            "ok": bool(per_tool) and all(v["p95_ms"] < LATENCY_TARGET_MS and v["bytes"] < REPLY_TARGET_BYTES for v in per_tool.values())}


def bench(code: str) -> dict:
    t0 = time.perf_counter()
    ProcessAPI(code, use_cache=False, telemetry=False)
    cold_rebuild = time.perf_counter() - t0
    t0 = time.perf_counter()
    api = ProcessAPI(code, telemetry=False)
    cold_cached = time.perf_counter() - t0
    out = {"project": code, "nodes": len(api.idx.keys), "edges": api.idx.n_edges,
           "cold_rebuild_s": round(cold_rebuild, 2), "cold_cached_s": round(cold_cached, 2),
           "target_p95_ms": LATENCY_TARGET_MS, **bench_api(api)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="devkb process API")
    ap.add_argument("--project", required=True)
    ap.add_argument("tool", help="one of: " + ", ".join(sorted(TOOL_ARGS)) + ", bench")
    ap.add_argument("args", nargs="*", help="positional arguments, then key=value")
    ns = ap.parse_args()
    if ns.tool == "bench":
        out = bench(ns.project)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if ns.tool not in TOOL_ARGS:
        print(json.dumps({"error": f"unknown tool {ns.tool}", "tools": sorted(TOOL_ARGS)}))
        return 2
    method, pos = TOOL_ARGS[ns.tool]
    kw: dict = {}
    plain = [a for a in ns.args if "=" not in a]
    if ns.tool in TEXT_TOOLS and plain:
        kw[pos[0]] = " ".join(plain)  # a symptom, goal or query is words, not one argument
    else:
        for name, value in zip(pos, plain):
            kw[name] = _coerce(name, value)
    for a in ns.args:
        if "=" in a:
            k, _, v = a.partition("=")
            kw[k] = _coerce(k, v)
    print(json.dumps(ProcessAPI(ns.project).call(method, **kw), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
