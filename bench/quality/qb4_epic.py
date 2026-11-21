#!/usr/bin/env python3
"""QB4 (docs/specs/quality-benchmarks.md): from a specification and a ticket's title, does a method predict the code the ticket's fix touches?

Items: tickets whose body names a SPEC id that has a document under docs/specs/ (leave one ticket out: each is predicted from its own
title and its spec's text; its body, which names files, is never used). Truth: the Python files under devkb/ and scripts/ changed by the
commits that cite the ticket. Candidates: those files as they are today. Arms:
  bm25    text retrieval; a file is its path words and the names defined in it; the query is the title (weighted) and the spec text
  grep    the title's identifier-like words, a file scored by how many appear in it
  graph   the names in the title (and, weaker, in the spec) resolved in the graph to files, plus the files that call into them
Metrics: file recall at 10 and 20, precision at 10; 90% interval resampling the specs (items of one spec share its text).
Caveat: today's tree contains names the fix itself added; every arm sees the same tree.   python bench/quality/qb4_epic.py"""
from __future__ import annotations

import collections
import math
import random
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import qb2_related as q2  # noqa: E402

STOP = set("the and for with that this from when then than into over under also each only does done make made must need not are was were has had its".split())


def spec_file(sid: str) -> Path | None:
    for p in sorted((ROOT / "docs" / "specs").glob(f"{sid}*.md")):
        return p
    return None


def main() -> None:
    iss = q2.issues()
    cm = q2.commits()
    g = q2.Graph()
    code = sorted(f for f in g.tracked if re.match(r"(devkb|scripts)/[\w/]*\.py$", f))
    r = g.r
    names_in: dict[str, list[str]] = collections.defaultdict(list)
    for i in r.ids:
        f = r.file[i]
        if f in set(code):
            names_in[f].append(r.short[i])
    docs = {f: q2.toks(f.replace("/", " ").replace(".py", " ") + " " + " ".join(names_in[f])) for f in code}
    bm = q2.BM25(docs)
    text_of = {f: (ROOT / f).read_text(errors="replace") for f in code}
    # dependents: the files that call into a file (1 hop), from the graph
    callers_of: dict[str, set[str]] = collections.defaultdict(set)
    for i in r.ids:
        f = r.file[i]
        if f not in set(code):
            continue
        for c in r.api.idx.sources("CALLS", i):
            cf = r.api._key(c).split("::")[0]
            if cf != f and cf in set(code):
                callers_of[f].add(cf)
    items = []
    for it in iss.values():
        sid = next((s for s in re.findall(r"SPEC-[A-Z]+-\d+", it["body"] or "") if spec_file(s)), None)
        if not sid:
            continue
        truth = {f for t, nums, fl in cm if it["number"] in nums for f in fl if f in set(code)}
        if truth:
            items.append((it["number"], sid, truth))
    items.sort()
    arms = ["bm25", "grep", "graph"]
    res = {a: [] for a in arms}
    spec_of = {}
    for num, sid, truth in items:
        title = q2.clean(iss[num]["title"])
        spec = q2.clean(spec_file(sid).read_text(errors="replace"))
        tt = [t for t in q2.toks(title) if t not in STOP]
        qtoks = tt * 3 + q2.toks(spec)
        r_bm = bm.rank(qtoks)
        words = {w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", title) if w.lower() not in STOP}
        sc = {f: sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text_of[f], re.I)) for f in code}
        r_gr = sorted(code, key=lambda f: (-sc[f], f)) if any(sc.values()) else []
        w = collections.defaultdict(float)
        for f, x in g.names_to_files(title).items():
            w[f] += x
        for f, x in g.names_to_files(spec).items():
            w[f] += 0.1 * x
        direct = dict(w)
        for f, x in direct.items():
            for c in callers_of.get(f, ()):
                w[c] += 0.3 * x
        r_gh = sorted((f for f in w if f in set(code)), key=lambda f: (-w[f], f)) if w else []
        for a, rk in (("bm25", r_bm), ("grep", r_gr), ("graph", r_gh)):
            top = lambda k: set(rk[:k])
            res[a].append({"item": num, "spec": sid, "r10": len(top(10) & truth) / len(truth), "r20": len(top(20) & truth) / len(truth),
                           "p10": len(top(10) & truth) / 10, "n": len(rk)})
            spec_of[num] = sid
    n = len(items)
    print(f"{n} items from {len(set(spec_of.values()))} specs ({', '.join(f'{s} {sum(1 for v in spec_of.values() if v == s)}' for s in sorted(set(spec_of.values())))}); "
          f"truth files per item: median {st.median(len(t) for _, _, t in items)}; candidate files {len(code)}\n")

    def ci(vals: dict[int, float]) -> tuple[float, float]:
        groups = collections.defaultdict(list)
        for i, v in vals.items():
            groups[spec_of[i]].append(v)
        keys, rnd = list(groups), random.Random(9)
        ms = sorted(st.mean([v for k in rnd.choices(keys, k=len(keys)) for v in groups[k]]) for _ in range(3000))
        return ms[150], ms[2849]
    print("| arm | recall@10 | recall@20 (90%, resampling specs) | precision@10 | answered |\n|---|---|---|---|---|")
    for a in arms:
        r20 = {x["item"]: x["r20"] for x in res[a]}
        lo, hi = ci(r20)
        print(f"| {a} | {st.mean(x['r10'] for x in res[a]):.2f} | {st.mean(r20.values()):.2f} ({lo:.2f}-{hi:.2f}) | {st.mean(x['p10'] for x in res[a]):.2f} | {sum(1 for x in res[a] if x['n'])}/{n} |")
    print("\nPaired recall@20 differences (90%, resampling specs):")
    for x, y in (("graph", "bm25"), ("graph", "grep"), ("bm25", "grep")):
        d = {a["item"]: a["r20"] - b["r20"] for a, b in zip(res[x], res[y])}
        lo, hi = ci(d)
        print(f"  {x} - {y}: {st.mean(d.values()):+.2f} ({lo:+.2f} to {hi:+.2f})")
    big = collections.Counter(f for _, _, t in items for f in t).most_common(3)
    print(f"\nthe three most-touched files carry {sum(c for _, c in big)} of {sum(len(t) for _, _, t in items)} truth entries: {[f for f, _ in big]}")
    pri = sorted(code, key=lambda f: -sum(1 for _, _, t in items if f in t))
    for k in (10, 20):
        print(f"popularity prior (the files most often touched by the other items), recall@{k}: "
              f"{st.mean(len(set(pri[:k]) & t) / len(t) for _, _, t in items):.2f} (in-sample: an upper bound for a prior)")


if __name__ == "__main__":
    main()
