#!/usr/bin/env python3
"""QB2 (docs/specs/quality-benchmarks.md): given a new issue, does a method find the issue it follows, and the code its fix
will touch? Offline, no model runs.

Items: issues that say "Follow-up of #N" or "duplicate of #N" (N an older issue). Truth: that N. The query is the issue's title
and body with every `#number` removed (the link and any other reference). Candidates: the issues numbered below the item.
Arms: bm25 (text), structural (the code names and paths the issue mentions, resolved in the graph to files, matched against the
files each candidate issue's commits changed before the item was filed), hybrid (reciprocal-rank fusion of the two).
Owner recall: the files changed by the commits of the issue's own fix (after it was filed) against the files of the arm's top 5.

  python bench/quality/qb2_related.py [--refresh]      (needs `gh`; caches the issues under ~/.cache/devkb/qb2)
"""
from __future__ import annotations

import collections
import json
import math
import os
import random
import re
import statistics as st
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / ".cache" / "devkb" / "qb2"
sys.path.insert(0, str(ROOT))


def issues() -> dict[int, dict]:
    f = CACHE / "issues.json"
    if not f.exists() or "--refresh" in sys.argv:
        CACHE.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(["gh", "issue", "list", "-R", "namiq-ai/devkb", "--state", "all", "--limit", "500", "--json",
                              "number,title,body,createdAt,state,labels"], capture_output=True, text=True, check=True).stdout
        f.write_text(out)
    return {i["number"]: i for i in json.loads(f.read_text())}


def when(i: dict) -> float:
    return datetime.fromisoformat(i["createdAt"].replace("Z", "+00:00")).timestamp()


def clean(text: str) -> str:
    return re.sub(r"#\d+|\b(?:issue|PR|ticket)\s+\d+\b", " ", text or "")


def toks(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        parts = [p for x in t.split("_") for p in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", x)]
        out += [p.lower() for p in parts if len(p) >= 3] + ([t.lower()] if "_" in t or len(parts) > 1 else [])
    return out


class BM25:
    def __init__(self, docs: dict[int, list[str]], k1=1.4, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = st.mean(len(d) for d in docs.values()) or 1
        df = collections.Counter(t for d in docs.values() for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + .5) / (c + .5)) for t, c in df.items()}
        self.tf = {k: collections.Counter(d) for k, d in docs.items()}

    def rank(self, query: list[str]) -> list[int]:
        q = collections.Counter(query)
        sc = {}
        for k, tf in self.tf.items():
            ln = len(self.docs[k])
            s = sum(self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * ln / self.avg)) for t in q if t in tf)
            sc[k] = s
        return sorted(sc, key=lambda k: (-sc[k], -k))


def commits() -> list[tuple[float, set[int], set[str]]]:
    """(time, issue numbers it cites, files it changed) for every first-parent commit of origin/main."""
    raw = subprocess.run(["git", "-C", str(ROOT), "log", "--first-parent", "-m", "--pretty=format:@@%at|%s|%b", "--name-only", "origin/main"],
                         capture_output=True, text=True).stdout
    out = []
    for blk in raw.split("@@")[1:]:
        head, _, files = blk.partition("\n")
        t, _, rest = head.partition("|")
        nums = {int(x) for x in re.findall(r"#(\d+)", rest)}
        for br in re.findall(r"(?:fix|feat|docs|bench|chore|refactor|test|release)/(\d+(?:-\d+)*)", rest):
            nums |= {int(x) for x in br.split("-") if len(x) >= 2}
        fl = {f for f in files.split("\n") if f.strip() and not f.startswith("@@")}
        out.append((float(t), nums, fl))
    return out


def files_of(num: int, before: float, cm) -> set[str]:
    return {f for t, nums, fl in cm if num in nums and t <= before for f in fl}


class Graph:
    def __init__(self):
        from devkb.process_api import ProcessAPI
        from devkb.read_tools import ReadTools
        self.r = ReadTools(ProcessAPI(str(ROOT)))
        self.r._tables()
        self.tracked = set(subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split())

    def names_to_files(self, text: str) -> dict[str, float]:
        """The files the code names and paths in the text point at, weighted by how few definitions each name has."""
        w: dict[str, float] = collections.defaultdict(float)
        for p in re.findall(r"[\w./-]+\.(?:py|h|cc|cpp|ts|md|json|yml|yaml|sh)\b", text):
            if p in self.tracked:
                w[p] += 1.0
            else:
                for f in self.tracked:
                    if f.endswith("/" + p):
                        w[f] += 0.5
        cands = set(re.findall(r"`([A-Za-z_][\w.:]*)`", text)) | set(re.findall(r"\b([A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z]\w+|[A-Z][a-z]+[A-Z]\w+)\b", text))
        for c in cands:
            n = c.split(".")[-1].split("::")[-1].lower()
            ids = self.r._by_name.get(n, [])
            if 0 < len(ids) <= 4 and (len(n) >= 5 or "_" in n):
                for i in ids:
                    w[self.r.file[i]] += 1.0 / len(ids)
        return dict(w)


def rrf(*ranks: list[int], k=60) -> list[int]:
    s = collections.defaultdict(float)
    for r in ranks:
        for pos, c in enumerate(r, 1):
            s[c] += 1.0 / (k + pos)
    return sorted(s, key=lambda c: (-s[c], -c))


def boot(xs, n=3000, seed=5):
    rnd = random.Random(seed)
    m = sorted(st.mean(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return m[int(.05 * n)], m[int(.95 * n) - 1]


def main() -> None:
    iss = issues()
    items = []
    for i in iss.values():
        refs = {int(x) for x in re.findall(r"(?:follow-up of|duplicate of|dup of) #(\d+)", i["body"] or "", re.I)}
        refs = {r for r in refs if r in iss and r < i["number"]}
        if refs:
            items.append((i["number"], refs))
    cm, g = commits(), Graph()
    arms = ["bm25", "structural", "hybrid"]
    res = {a: [] for a in arms}
    own = {a: [] for a in arms}
    for num, truth in sorted(items):
        it = iss[num]
        pool = [k for k in iss if k < num]
        docs = {k: toks(clean((iss[k]["title"] or "") + " " + (iss[k]["body"] or ""))) for k in pool}
        q = clean((it["title"] or "") + " " + (it["body"] or ""))
        bm = BM25(docs).rank(toks(q))
        qf = g.names_to_files(q)
        cf = {k: files_of(k, when(it), cm) | set(g.names_to_files((iss[k]["title"] or "") + " " + (iss[k]["body"] or ""))) for k in pool}
        df = collections.Counter(f for s in cf.values() for f in s)
        idf = {f: math.log(1 + len(pool) / c) for f, c in df.items()}
        sc = {k: sum(w * idf.get(f, 0) for f, w in qf.items() if f in cf[k]) for k in pool}
        st_rank = sorted(pool, key=lambda k: (-sc[k], -k))
        if not any(sc.values()):
            st_rank = []                                                  # nothing in the text maps to a file: no answer, not a guess
        hy = rrf(bm, st_rank) if st_rank else bm
        own_files = {f for t, nums, fl in cm if num in nums and t >= when(it) for f in fl}
        for a, r in (("bm25", bm), ("structural", st_rank), ("hybrid", hy)):
            pos = next((p for p, c in enumerate(r, 1) if c in truth), 10 ** 6)
            res[a].append({"item": num, "rank": pos, "answered": bool(r)})
            top = {f for c in r[:5] for f in cf[c]}
            own[a].append(len(top & own_files) / len(own_files) if own_files else None)
    n = len(items)
    print(f"{n} items; {len({p for _, t in items for p in t})} distinct parents; candidates per item: all older issues (median {st.median(len([k for k in iss if k < i]) for i, _ in items)})\n")
    print("| arm | answered | R@1 | R@5 | R@10 | MRR | owner-file recall at 5 |\n|---|---|---|---|---|---|---|")
    for a in arms:
        rk = [r["rank"] for r in res[a]]
        r5 = [1.0 if x <= 5 else 0.0 for x in rk]
        lo, hi = boot(r5)
        ow = [x for x in own[a] if x is not None]
        print(f"| {a} | {sum(r['answered'] for r in res[a])}/{n} | {st.mean(1.0 if x <= 1 else 0.0 for x in rk):.2f} | {st.mean(r5):.2f} ({lo:.2f}-{hi:.2f}) | "
              f"{st.mean(1.0 if x <= 10 else 0.0 for x in rk):.2f} | {st.mean(1 / x if x < 10 ** 6 else 0 for x in rk):.2f} | {st.mean(ow):.2f} (n={len(ow)}) |")
    pri = collections.Counter(p for _, t in items for p in t)
    top1 = pri.most_common(1)[0]
    print(f"\nprior: the most-followed parent (#{top1[0]}) is the truth of {top1[1]} of {n} items ({100 * top1[1] // n}%)")
    (CACHE / "qb2-results.json").write_text(json.dumps({"res": res, "own": own}, indent=1))


if __name__ == "__main__":
    main()
