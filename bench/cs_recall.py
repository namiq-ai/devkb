"""Caller-file recall and precision of the C# graph, on methods whose name is unique (SPEC-DEVKB-CSHARP-3).

  python bench/cs_recall.py REPO [--ref GIT_REF_OR_FILE] [--n 150] [--seed 2032] [--show]

With --ref, the baseline and the current extractor are measured on the same methods (unique in both).

What a `devkb pack refactor NAME` answer lists is the files with a direct caller. For a method whose name is defined
once in the whole repository (and is not a common .NET member name), the files that call it are, to a close
approximation, the files whose code contains `NAME(` or `NAME<...>(` outside the definition: comments and strings
are masked first. That is the truth here. The graph's answer is the files of its CALLS edges into the method.

recall    = truth files the graph lists / truth files
precision = graph files that are in the truth / graph files

The truth over-approximates where an outside library has a method of the same name (calls to it are not calls to
ours); names that .NET's own common types define are excluded for that reason (`csharp_dotnet.MEMBERS`). Reads
source only; writes nothing.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(ref: str | None):
    if not ref:
        from devkb import csharp_symbols
        return csharp_symbols
    src = Path(ref).read_text() if Path(ref).is_file() else subprocess.run(
        ["git", "show", f"{ref}:devkb/csharp_symbols.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("cs_old", loader=None))
    sys.modules["cs_old"] = mod
    exec(src, mod.__dict__)
    return mod


def common_names() -> set[str]:
    try:
        from devkb import csharp_dotnet
        return set().union(*csharp_dotnet.MEMBERS.values()) | set(getattr(csharp_dotnet, "DOTNET_EXTENSIONS", ())) \
            | set(getattr(csharp_dotnet, "LINQ_LAMBDA", ())) | set(getattr(csharp_dotnet, "LINQ_TO", ()))
    except ImportError:                                   # before round 3 there is no table: a small fixed list
        return set("Add Remove Contains Get Set Create Find Execute ExecuteAsync Run Dispose ToString Equals "
                   "GetHashCode Clear Update Delete Load Save Parse TryParse Count Any First Where Select".split())


def _unique(symbols, skip) -> dict[str, dict]:
    by_name: dict[str, list[dict]] = {}
    for s in symbols:
        if s["kind"] in ("method", "function", "class", "enum"):
            by_name.setdefault(s["name"], []).append(s)
    return {name: ss[0] for name, ss in by_name.items()
            if len(ss) == 1 and ss[0]["kind"] == "method" and len(name) >= 6 and name not in skip
            and name != "ctor" and not ss[0].get("is_test") and "Test" not in name}


def _score(name: str, s: dict, calls_by_callee: dict, masked: dict) -> tuple[set, set]:
    pat = re.compile(r"(?<![\w.])(?:[\w]+\s*\??\.\s*)*" + re.escape(name) + r"\s*(?:<[^<>();]*>)?\s*\(|\." +
                     re.escape(name) + r"\s*(?:<[^<>();]*>)?\s*\(")
    truth = set()
    for rel, text in masked.items():
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            if rel == s["rel"] and s["line_start"] <= line <= s["line_end"]:
                continue                                          # the definition, or recursion (no edge by design)
            truth.add(rel)
            break
    return truth, calls_by_callee.get(s["key"], set())


def _arm(cs, repo: Path):
    symbols, calls = cs.extract(repo)
    by_callee: dict[str, set[str]] = {}
    for c in calls:
        by_callee.setdefault(c["callee"], set()).add(c["rel"])
    return symbols, by_callee


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--ref", default=None, help="baseline csharp_symbols.py (a git ref of devkb, or a file): both arms "
                                                "are measured on the same methods")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=2032)
    ap.add_argument("--show", action="store_true", help="print each method's missed and extra files")
    a = ap.parse_args()
    repo = Path(a.repo)
    skip = common_names()
    arms = {"new": load(None)}
    if a.ref:
        arms = {"base": load(a.ref), **arms}
    built = {k: _arm(cs, repo) for k, cs in arms.items()}
    # the same methods for every arm: unique by name in each arm's symbols
    uniq = [_unique(built[k][0], skip) for k in built]
    names = sorted(set.intersection(*(set(u) for u in uniq)))
    random.seed(a.seed)
    picked = sorted(random.sample(names, min(a.n, len(names))))
    cs = arms["new"]
    masked = {}
    for rel in cs.list_files(repo):
        p = repo / rel
        if p.is_file() and p.stat().st_size <= 2_000_000:
            masked[rel] = cs.mask(p.read_text(errors="replace"))
    out = {"repo": repo.name, "methods": len(picked)}
    for k, u in zip(built, uniq):
        tt = tg = th = with_callers = 0
        for name in picked:
            truth, graph = _score(name, u[name], built[k][1], masked)
            hit = truth & graph
            tt, tg, th, with_callers = tt + len(truth), tg + len(graph), th + len(hit), with_callers + bool(truth)
            if a.show and (truth - graph or graph - truth):
                print(f"  [{k}] {name}: missed {sorted(truth - graph)[:4]} extra {sorted(graph - truth)[:4]}")
        out[k] = {"with_callers": with_callers, "truth_files": tt, "graph_files": tg, "hits": th,
                  "recall": round(th / tt, 3) if tt else None, "precision": round(th / tg, 3) if tg else None}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
