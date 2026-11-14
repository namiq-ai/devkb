"""A long-lived, compact index over a project's `.devkb/` store (ODSF-306).

`devkb/index.py` re-reads every JSONL line on each CLI call, which is 98 MB for
OCO and was never measured. This keeps one integer-addressed index in memory,
persists it next to the graph, and reloads only when the graph changes. It
answers the process API (`devkb/process_api.py`) and the MCP server
(`devkb/mcp_server.py`); the generic `index.py` is left alone for its other
callers.

Staleness is explicit. Every reply says which commit the graph was built at and
whether the repository has moved on, so an agent knows when to trust it.
"""
from __future__ import annotations

import json
import pickle
import re
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CACHE_VERSION = 9
CACHE_NAME = ".process-index.pkl"
TELEMETRY_NAME = "process-api-telemetry.jsonl"

# Only the properties the process API reads, so a reply is short and the cache is small.
KEEP_PROPS = {
    "Ticket": ("title", "ticket_type", "priority", "status", "component", "assignee", "issue_path"),
    "Spec": ("title", "doc_type", "status", "spec_id"),
    "Symbol": ("kind", "line_start", "line_end", "complexity", "is_public", "docstring_summary",
               "unresolved_calls", "unresolved_files"),  # ODSF-313: what a list answer cannot see
    "ErrorSignature": ("kind", "label", "message_template", "status_code"),
    "TestCase": ("function", "file", "line"),
    "Commit": ("short_hash", "subject", "date"),
    "Endpoint": ("method", "path", "owner_symbol"),
    "Flow": ("touch_point_kind", "step_count"),
    "Warning": ("rule", "severity", "detail"),
    "WorkPackage": ("title", "status"),
    "ConfigKey": ("kind",),                                   # ADR-SDP-DEVKB-005 (ODSF-312)
    "Component": ("kind", "label", "file", "image", "ports", "exec", "path"),
    "Repository": ("role",),
}
_WORD = re.compile(r"[a-z0-9]{3,}")


def stem(w: str) -> str:
    """Strip the common English endings so "saving records" finds `save_record`. Deliberately crude and applied the
    same way to the index and to the query: a stem need not be a word, only the same on both sides."""
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and not (suffix == "s" and w.endswith("ss")):
            w = w[: -len(suffix)]
            break
    return w[:-1] if w.endswith("e") and len(w) > 3 else w


def words(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(text.lower().replace("_", " ").replace("-", " ").replace("/", " ").replace(".", " "))]


@dataclass
class CompactIndex:
    code: str
    repo_root: str
    built_at: str = ""
    git_head: str = ""
    types: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    props: list[dict] = field(default_factory=list)
    by_key: dict[tuple[str, str], int] = field(default_factory=dict)
    short: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    sym_by_file: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    out: dict[str, dict[int, list[int]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(list)))
    inn: dict[str, dict[int, list[int]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(list)))
    sim: dict[int, list[tuple[int, float]]] = field(default_factory=lambda: defaultdict(list))
    ep_by_owner: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    spec_terms: dict[int, tuple[list[str], list[str], list[str]]] = field(default_factory=dict)
    spec_df: dict[str, int] = field(default_factory=dict)
    spec_inv: dict[str, list[int]] = field(default_factory=dict)   # token -> specs containing it (ODSF-309)
    flow_steps: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # flow -> [(sequence, step)] (ODSF-311)
    spec_heads: dict[int, list[str]] = field(default_factory=dict)              # spec -> its first headings (ODSF-311)
    spec_by_id: dict[str, int] = field(default_factory=dict)        # lower-case spec id -> spec
    type_count: dict[str, int] = field(default_factory=dict)        # node type -> count, computed once
    code_inv: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # word -> (symbol, weight): name 3, path 2, docstring 1
    err_inv: dict[str, list[int]] = field(default_factory=dict)     # word of an error message -> ErrorSignature nodes
    ticket_inv: dict[str, list[int]] = field(default_factory=dict)  # word of a ticket title -> tickets
    n_symbols: int = 0
    n_edges: int = 0

    # ── lookups ────────────────────────────────────────────────────────────
    def node(self, node_type: str, key: str) -> int | None:
        return self.by_key.get((node_type, key))

    def targets(self, verb: str, src: int) -> list[int]:
        return self.out[verb].get(src, []) if verb in self.out else []

    def sources(self, verb: str, dst: int) -> list[int]:
        return self.inn[verb].get(dst, []) if verb in self.inn else []

    def type_counts(self) -> dict[str, int]:
        return self.type_count


def _read_manifest(devkb_dir: Path) -> dict:
    try:
        return json.loads((devkb_dir / "manifest.json").read_text())
    except (OSError, ValueError):
        return {}


def _signature(devkb_dir: Path) -> list:
    sig: list = [CACHE_VERSION]
    for name in ("nodes.jsonl", "edges.jsonl", "manifest.json"):
        try:
            st = (devkb_dir / name).stat()
            sig += [name, st.st_size, st.st_mtime_ns]
        except OSError:
            sig += [name, None, None]
    return sig


def _build(code: str, repo_root: Path, devkb_dir: Path) -> CompactIndex:
    manifest = _read_manifest(devkb_dir)
    idx = CompactIndex(code=code, repo_root=str(repo_root), built_at=manifest.get("built_at", ""),
                       git_head=manifest.get("git_head", ""))
    uid_to_i: dict[str, int] = {}
    for line in (devkb_dir / "nodes.jsonl").read_text().splitlines():
        if not line:
            continue
        n = json.loads(line)
        i = len(idx.types)
        t, key = n["type"], n["natural_key"]
        uid_to_i[n["uid"]] = i
        idx.types.append(t)
        idx.keys.append(key)
        wanted = KEEP_PROPS.get(t)
        idx.props.append({k: n["properties"][k] for k in wanted if k in n["properties"]} if wanted else {})
        idx.by_key[(t, key)] = i
        if t == "Symbol":
            path, _, qual = key.partition("::")
            idx.short[qual.rsplit(".", 1)[-1]].append(i)
            idx.sym_by_file[path].append(i)
        elif t == "Endpoint" and n["properties"].get("owner_symbol"):
            idx.ep_by_owner[n["properties"]["owner_symbol"]].append(i)
    for line in (devkb_dir / "edges.jsonl").read_text().splitlines():
        if not line:
            continue
        e = json.loads(line)
        a, b = uid_to_i.get(e["from_uid"]), uid_to_i.get(e["to_uid"])
        if a is None or b is None:
            continue
        verb = e["verb"]
        idx.out[verb][a].append(b)
        idx.inn[verb][b].append(a)
        idx.n_edges += 1
        if verb == "SIMILAR_TO":
            idx.sim[a].append((b, float(e["properties"].get("weighted_score") or 0.0)))
        elif verb == "STEP":
            idx.flow_steps.setdefault(a, []).append((int(e["properties"].get("sequence") or 0), b))
    for lst in idx.sim.values():
        lst.sort(key=lambda p: -p[1])
        del lst[8:]
    for steps in idx.flow_steps.values():
        steps.sort()
    # Spec search terms: title, path and the first headings of each document, read once.
    df: dict[str, int] = defaultdict(int)
    inv: dict[str, list[int]] = {}
    for i, t in enumerate(idx.types):
        if t != "Spec":
            continue
        path = idx.keys[i]
        heads: list[str] = []
        try:
            with open(repo_root / path, errors="replace") as fh:
                for _ in range(120):
                    ln = fh.readline()
                    if not ln:
                        break
                    if ln.startswith("#"):
                        heads.append(ln.lstrip("# ").strip())
        except OSError:
            pass
        title_w = words(idx.props[i].get("title", "") + " " + str(idx.props[i].get("spec_id") or ""))
        path_w = words(path)
        head_w = words(" ".join(heads))
        idx.spec_terms[i] = (title_w, path_w, head_w)
        idx.spec_heads[i] = heads[:12]
        for w in set(title_w) | set(path_w) | set(head_w):
            df[w] += 1
            inv.setdefault(w, []).append(i)
        sid = str(idx.props[i].get("spec_id") or "").strip().lower()
        if sid:
            idx.spec_by_id[sid] = i
    idx.spec_df = dict(df)
    idx.spec_inv = inv
    counts: dict[str, int] = defaultdict(int)
    for t in idx.types:
        counts[t] += 1
    idx.type_count = dict(counts)
    idx.n_symbols = counts.get("Symbol", 0)
    # Word indexes for the developer-task tools (ODSF-310): find code by what it is called and says, an error by its
    # message, a past ticket by its title. Built once with the graph, so a query is a few dictionary lookups.
    for i, t in enumerate(idx.types):
        if t == "Symbol":
            path, _, qual = idx.keys[i].partition("::")
            weight: dict[str, int] = {}
            for w in words(qual):
                weight[w] = 3
            for w in words(path):
                weight[w] = max(weight.get(w, 0), 2)
            for w in words(idx.props[i].get("docstring_summary") or ""):
                weight[w] = max(weight.get(w, 0), 1)
            for w, wt in weight.items():
                idx.code_inv.setdefault(w, []).append((i, wt))
        elif t == "ErrorSignature":
            p = idx.props[i]
            for w in set(words((p.get("message_template") or "") + " " + (p.get("label") or ""))):
                idx.err_inv.setdefault(w, []).append(i)
        elif t == "Ticket":
            for w in set(words(idx.props[i].get("title") or "")):
                idx.ticket_inv.setdefault(w, []).append(i)
    # Plain dicts only: a defaultdict built from a lambda cannot be pickled.
    idx.short, idx.sym_by_file = dict(idx.short), dict(idx.sym_by_file)
    idx.ep_by_owner, idx.sim = dict(idx.ep_by_owner), dict(idx.sim)
    idx.out = {v: dict(m) for v, m in idx.out.items()}
    idx.inn = {v: dict(m) for v, m in idx.inn.items()}
    return idx


def load_index(code: str, repo_root: Path, devkb_dir: Path, use_cache: bool = True) -> CompactIndex:
    """Read the cache when it still matches the graph files, else rebuild and save it."""
    cache = devkb_dir / CACHE_NAME
    sig = _signature(devkb_dir)
    if use_cache and cache.exists():
        try:
            with open(cache, "rb") as fh:
                saved_sig, idx = pickle.load(fh)
            if saved_sig == sig:
                return idx
        except Exception:  # a stale or corrupt cache is rebuilt, never trusted
            pass
    idx = _build(code, repo_root, devkb_dir)
    try:
        with open(cache, "wb") as fh:
            pickle.dump((sig, idx), fh, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass
    return idx


class Staleness:
    """Whether the repository has moved past the commit the graph was built at.

    The first call answers synchronously. After that the answer is refreshed in a background thread when it is
    older than `ttl` seconds, so no tool call ever waits on `git` for it (ODSF-309: a synchronous refresh every
    5 seconds put a 5 to 30 ms spike on whichever call happened to land in the window)."""

    def __init__(self, repo_root: Path, built_head: str, ttl: float = 5.0) -> None:
        self.repo_root, self.built_head, self.ttl = repo_root, built_head, ttl
        self._at = 0.0
        self._value = (False, "", 0)
        self._busy = False

    def _refresh(self) -> None:
        head, behind = "", 0
        try:
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True,
                                  text=True, timeout=5).stdout.strip()
            if head and self.built_head and head != self.built_head:
                out = subprocess.run(["git", "rev-list", "--count", f"{self.built_head}..HEAD"], cwd=self.repo_root,
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                behind = int(out) if out.isdigit() else 0
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        self._value = (bool(head and self.built_head and head != self.built_head), head, behind)
        self._at = time.monotonic()
        self._busy = False

    def check(self) -> tuple[bool, str, int]:
        if self._at == 0.0:
            self._refresh()
        elif time.monotonic() - self._at >= self.ttl and not self._busy:
            self._busy = True
            threading.Thread(target=self._refresh, daemon=True).start()
        return self._value


class Telemetry:
    """One JSON line per call: tool, milliseconds, reply bytes. This is how the
    API is dogfooded and how the benchmark proves what the graph returned."""

    def __init__(self, devkb_dir: Path, enabled: bool = True) -> None:
        self.path = devkb_dir / TELEMETRY_NAME
        self.enabled = enabled

    def log(self, tool: str, ms: float, size: int, ok: bool, **extra) -> None:
        if not self.enabled:
            return
        try:
            with open(self.path, "a") as fh:
                fh.write(json.dumps({"t": round(time.time(), 3), "tool": tool, "ms": round(ms, 2),
                                     "bytes": size, "ok": ok, **extra}) + "\n")
        except OSError:
            pass
