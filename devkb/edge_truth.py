#!/usr/bin/env python3
"""Precision and recall of each edge family, against truth computed from the source, never from devkb (ODSF-314).

  python3 devkb/edge_truth.py --dir <graph dir> --repo <checkout it was built from> [--json OUT] [--seed 314]

Truth per family (sampled where the full set is large, seeded):
  CALLS          import-resolved AST callers of uniquely named functions (devkb/bench/workflow_tasks.callers_of),
                 recall and precision, and precision per resolution source
  inheritance    CALLS resolved only through a base class (source ast-typed-receiver-base): count, and the share whose
                 caller's own body calls that method name on something (a necessary, not sufficient, condition)
  TESTED_BY      per source: the share of edges whose test function's body calls a function defined in the target
  SIMILAR_TO     the share of a ticket's kept neighbours in the same epic or component, against random pairs
  CALLS_API      frontend fetch/wrapper URLs (template literals normalised) matched to route paths: file-level recall
  RAISES         AST `raise X("literal")` in uniquely named functions: recall
  READS          literal os.environ / os.getenv reads in non-test files: file-level recall
  coverage       of functions the graph marks complete, the share whose graph callers include every true caller
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import random
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "bench"))
import workflow_tasks as wt  # noqa: E402


def load(d: Path):
    nodes, by_uid = {}, {}
    for line in (d / "nodes.jsonl").read_text().splitlines():
        if line:
            n = json.loads(line)
            by_uid[n["uid"]] = n
            nodes[(n["type"], n["natural_key"])] = n
    edges = collections.defaultdict(list)
    for line in (d / "edges.jsonl").read_text().splitlines():
        if line:
            e = json.loads(line)
            a, b = by_uid.get(e["from_uid"]), by_uid.get(e["to_uid"])
            if a and b:
                edges[e["verb"]].append((a, b, e.get("properties") or {}))
    return nodes, edges


def short(key: str) -> str:
    path, _, qual = key.partition("::")
    return f"{path}::{qual.split('.')[-1]}"


def f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


def calls_family(s, unique, edges, rnd, sample=200):
    callers_in = collections.defaultdict(set)
    by_src = collections.defaultdict(list)
    for a, b, p in edges["CALLS"]:
        callers_in[short(b["natural_key"])].add(short(a["natural_key"]))
        by_src[p.get("source", "?")].append((short(a["natural_key"]), short(b["natural_key"])))
    pool = [(n, k) for n, k in unique.items() if not wt.is_test_file(k[0]) and wt.callers_of(s, n)]
    rnd.shuffle(pool)
    tp = fn = fp = 0
    truth_pairs = set()
    complete_flags = []
    for name, key in pool[:sample]:
        truth = {wt.short(c) for c in wt.callers_of(s, name)}
        got = callers_in.get(wt.short(key), set())
        tp += len(truth & got)
        fn += len(truth - got)
        fp += len(got - truth)
        truth_pairs |= {(c, wt.short(key)) for c in truth}
    src_prec = {}
    for src_name, pairs in by_src.items():
        judged = [(a, b) for a, b in pairs if b.split("::")[-1] in unique and unique[b.split("::")[-1]] and wt.short(unique[b.split("::")[-1]]) == b]
        if judged:
            ok = sum(1 for a, b in judged if (a, b) in truth_pairs or a in {wt.short(c) for c in wt.callers_of(s, b.split("::")[-1])})
            src_prec[src_name] = {"judged": len(judged), "precision": round(ok / len(judged), 3)}
    rec, prec = tp / max(1, tp + fn), tp / max(1, tp + fp)
    return {"sample": min(sample, len(pool)), "recall": round(rec, 3), "precision": round(prec, 3), "f1": round(f1(prec, rec), 3),
            "edges_by_source": {k: len(v) for k, v in by_src.items()}, "precision_by_source": src_prec}


def inheritance_family(s, edges, rnd):
    base = [(a, b) for a, b, p in edges["CALLS"] if p.get("source") == "ast-typed-receiver-base"]
    ok = 0
    for a, b in base:
        key = (a["natural_key"].split("::")[0], a["natural_key"].split("::", 1)[1])
        meth = b["natural_key"].split(".")[-1]
        if any(called == meth for _kind, _base, called in s["calls"].get(key, ())):
            ok += 1
    sample = rnd.sample(base, min(8, len(base)))
    return {"edges": len(base), "caller_calls_that_name": round(ok / max(1, len(base)), 3),
            "examples": [f"{a['natural_key']} -> {b['natural_key']}" for a, b in sample]}


def _test_calls(root: Path, test_key: str, cache: dict) -> set[str]:
    """Names called inside the test function at `path:line` (a TestCase natural key)."""
    path, _, line = test_key.rpartition(":")
    if path not in cache:
        try:
            cache[path] = ast.parse((root / path).read_text(errors="replace"))
        except (OSError, SyntaxError, ValueError):
            cache[path] = None
    tree = cache[path]
    if tree is None or not line.isdigit():
        return set()
    at = int(line)
    # the innermost function enclosing the line: a marker edge points at where the test names the ticket
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= at <= getattr(n, "end_lineno", n.lineno):
            if best is None or n.lineno > best.lineno:
                best = n
    if best is None:
        return set()
    return {c.func.id if isinstance(c.func, ast.Name) else c.func.attr for c in ast.walk(best)
            if isinstance(c, ast.Call) and isinstance(c.func, (ast.Name, ast.Attribute))}


def tested_by_family(root, s, edges, rnd, sample=600):
    defs_by_file = collections.defaultdict(set)
    for name, keys in s["defs"].items():
        for path, _q in keys:
            defs_by_file[path].add(name)
    by_src = collections.defaultdict(list)
    for a, b, p in edges["TESTED_BY"]:
        by_src[p.get("source", "?")].append((a, b))
    cache: dict = {}
    out = {}
    for src_name, pairs in by_src.items():
        pick = rnd.sample(pairs, min(sample, len(pairs)))
        ok = 0
        for a, b in pick:
            called = _test_calls(root, b["natural_key"], cache)
            if a["type"] == "Symbol":
                target = {a["natural_key"].split(".")[-1].split("::")[-1]}
            else:
                target = defs_by_file.get(a["natural_key"], set())
            ok += bool(called & target)
        out[src_name] = {"edges": len(pairs), "judged": len(pick), "precision": round(ok / max(1, len(pick)), 3)}
    return out


def similar_family(nodes, edges, rnd):
    parent, comp = {}, {}
    for (t, k), n in nodes.items():
        if t == "Ticket":
            comp[k] = (n.get("properties") or {}).get("component")
    for a, b, _p in edges["CHILD_OF"]:
        parent[a["natural_key"]] = b["natural_key"]

    def related(x, y):
        return (parent.get(x) and parent.get(x) == parent.get(y)) or (comp.get(x) and comp.get(x) == comp.get(y))

    kept = collections.defaultdict(list)
    for a, b, p in edges["SIMILAR_TO"]:
        kept[a["natural_key"]].append((float(p.get("weighted_score") or 0), b["natural_key"]))
    top = [(x, y) for x, lst in kept.items() for _s, y in sorted(lst, reverse=True)[:8]]
    tickets = [k for (t, k) in nodes if t == "Ticket"]
    rand = [(rnd.choice(tickets), rnd.choice(tickets)) for _ in range(5000)]
    return {"edges": len(edges["SIMILAR_TO"]), "tickets_with_neighbours": len(kept),
            "edges_per_ticket": round(len(edges["SIMILAR_TO"]) / max(1, len(kept)), 1),
            "precision_at_8": round(sum(1 for x, y in top if related(x, y)) / max(1, len(top)), 3),
            "random_pair_rate": round(sum(1 for x, y in rand if x != y and related(x, y)) / len(rand), 3)}


_URL = re.compile(r"""(?:fetch|apiFetch|api|request|get|post|put|patch|del|delete)\s*(?:<[^>]*>)?\(\s*([`'"])(.*?)\1""", re.S)


def calls_api_family(root, nodes, edges):
    routes = []
    for (t, k), n in nodes.items():
        if t == "Endpoint" and (n.get("properties") or {}).get("owner_symbol"):
            path = (n["properties"].get("path") or k.split(" ", 1)[-1]).rstrip("/")
            routes.append(re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$"))
    files = subprocess.run(["git", "ls-files", "--", "*.ts", "*.tsx", "*.js", "*.jsx"], cwd=root, capture_output=True, text=True).stdout.split()
    truth = set()
    for rel in files:
        if "node_modules" in rel or rel.endswith(".d.ts"):
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        for _q, url in _URL.findall(text):
            path = re.sub(r"\$\{[^}]*\}", "x", url.split("?")[0])
            path = re.sub(r"^\$\{[^}]*\}|^https?://[^/]+", "", path).rstrip("/")
            if path.startswith("/") and any(r.match(path) for r in routes):
                truth.add(rel)
    got = {a["natural_key"].split("::")[0] for a, _b, _p in edges["CALLS_API"]}
    return {"frontend_files_calling_a_route": len(truth), "graph_files": len(got & truth) if truth else len(got),
            "recall": round(len(got & truth) / max(1, len(truth)), 3), "edges": len(edges["CALLS_API"])}


def raises_family(s, unique, edges):
    truth = {(wt.short(k), msg) for k, msg in s["raises"] if unique.get(k[1].split(".")[-1]) == k}
    got = {(short(a["natural_key"]), (b.get("properties") or {}).get("message_template")) for a, b, _p in edges["RAISES"]}
    got_fn = {x for x, _ in got}
    hit = sum(1 for fn, _msg in truth if fn in got_fn)
    return {"truth": len(truth), "recall_by_function": round(hit / max(1, len(truth)), 3)}


_READ = re.compile(r"""os\.(?:environ(?:\.get|\.setdefault)?\s*[\[(]|getenv\s*\()\s*['"]([A-Z][A-Z0-9_]+)['"]""")


def reads_family(root, edges):
    files = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.py"], cwd=root, capture_output=True, text=True).stdout.split()
    truth = set()
    for rel in files:
        if wt.is_test_file(rel) or re.search(r"(^|/)tests?/", rel):
            continue
        try:
            for name in _READ.findall((root / rel).read_text(errors="replace")):
                truth.add((rel, name))
        except OSError:
            continue
    got = {(a["natural_key"].split("::")[0], b["natural_key"]) for a, b, _p in edges["READS"]}
    return {"truth": len(truth), "recall": round(len(truth & got) / max(1, len(truth)), 3), "graph": len(got)}


def coverage_family(s, unique, nodes, edges, rnd, sample=200):
    callers_in = collections.defaultdict(set)
    for a, b, _p in edges["CALLS"]:
        callers_in[b["natural_key"]].add(short(a["natural_key"]))
    pool = [(n, k) for n, k in unique.items() if not wt.is_test_file(k[0]) and wt.callers_of(s, n)]
    rnd.shuffle(pool)
    marked = honest = 0
    for name, key in pool[:sample]:
        node = nodes.get(("Symbol", f"{key[0]}::{key[1]}"))
        if not node or (node.get("properties") or {}).get("unresolved_calls"):
            continue
        marked += 1
        truth = {wt.short(c) for c in wt.callers_of(s, name)}
        honest += truth <= callers_in.get(node["natural_key"], set())
    return {"marked_complete": marked, "truly_complete": round(honest / max(1, marked), 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json")
    ap.add_argument("--seed", type=int, default=314)
    ns = ap.parse_args()
    root, d = Path(ns.repo), Path(ns.dir)
    nodes, edges = load(d)
    s = wt.scan(root)
    unique = {n: ks[0] for n, ks in s["defs"].items() if len(ks) == 1 and not n.startswith("test_") and not n.startswith("__")}
    out = {"graph": str(d), "repo": str(root),
           "CALLS": calls_family(s, unique, edges, random.Random(ns.seed)),
           "inheritance": inheritance_family(s, edges, random.Random(ns.seed)),
           "TESTED_BY": tested_by_family(root, s, edges, random.Random(ns.seed)),
           "SIMILAR_TO": similar_family(nodes, edges, random.Random(ns.seed)),
           "CALLS_API": calls_api_family(root, nodes, edges),
           "RAISES": raises_family(s, unique, edges),
           "READS": reads_family(root, edges),
           "coverage": coverage_family(s, unique, nodes, edges, random.Random(ns.seed))}
    print(json.dumps(out, indent=1))
    if ns.json:
        Path(ns.json).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
