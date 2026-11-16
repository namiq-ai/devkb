#!/usr/bin/env python3
"""Which name-matching tiers earn their place? Prototype matcher, evaluated on real symbol names.

  name_matching.py GRAPH_DIR [GRAPH_DIR ...]

Tiers: A exact; B + suffix/prefix/substring; C + word overlap (snake/camel); D + edit similarity (difflib, trigram prefilter).
Queries are made from real symbols: exact, one typo, two words of the name, lower-cased, a qualified prefix; and negatives
(names taken from another repository) to measure false accepts. Success at k = a symbol with the target's short name is in the
top k. Output: a table per repository."""
import collections, difflib, json, random, re, sys
from pathlib import Path

def words(s):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]

def load(graph):
    syms = []
    for l in open(Path(graph) / "nodes.jsonl"):
        n = json.loads(l)
        if n["type"] == "Symbol" and n["properties"].get("kind") in ("function", "method", "class"):
            f, q = n["natural_key"].split("::", 1)
            if re.search(r"(^|/)(tests?|spec)/|_test\b|test_", f): continue
            syms.append((f, q, q.rsplit(".", 1)[-1].split("::")[-1]))
    return syms

class Matcher:
    def __init__(self, syms):
        self.syms = syms
        self.by_short = collections.defaultdict(list)
        self.tri = collections.defaultdict(set)
        self.names = sorted({s[2] for s in syms})
        for i, n in enumerate(self.names):
            low = n.lower()
            for j in range(len(low) - 2): self.tri[low[j:j + 3]].add(i)
        self.low = [n.lower() for n in self.names]
        self.w = [set(words(n)) for n in self.names]
    def rank(self, q, tier):
        ql = q.lower(); out = {}
        for i, n in enumerate(self.names):
            pass
        # A exact
        for i in self.tri_candidates(ql, tier):
            n, nl = self.names[i], self.low[i]; s = 0
            if n == q: s = 100
            elif nl == ql: s = 95
            elif tier >= 1 and nl.startswith(ql): s = 70 + 10 * len(ql) / len(nl)
            elif tier >= 1 and ql in nl: s = 50 + 10 * len(ql) / len(nl)
            elif tier >= 1 and nl in ql: s = 40
            if tier >= 2 and s < 60:
                qw = set(words(q)); ov = len(qw & self.w[i]) / max(1, len(qw | self.w[i]))
                if ov: s = max(s, 55 * ov + (10 if qw <= self.w[i] else 0))
            if tier >= 3 and s < 55:
                r = difflib.SequenceMatcher(None, ql, nl).ratio()
                if r >= 0.6: s = max(s, 60 * r)
            if s: out[i] = s
        return sorted(out.items(), key=lambda kv: -kv[1])[:20]
    def tri_candidates(self, ql, tier):
        if tier == 0:
            return [i for i, n in enumerate(self.low) if n == ql]
        cand = collections.Counter()
        for j in range(len(ql) - 2):
            for i in self.tri.get(ql[j:j + 3], ()): cand[i] += 1
        for w in words(ql):
            for i, ws in enumerate(self.w):
                if w in ws: cand[i] += 1
        need = 1
        return [i for i, c in cand.items() if c >= need][:4000] or ([] if tier < 3 else [])

def typo(s, rnd):
    if len(s) < 5: return s
    k = rnd.choice(("swap", "drop", "sub")); i = rnd.randrange(1, len(s) - 1)
    if k == "swap": return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if k == "drop": return s[:i] + s[i + 1:]
    return s[:i] + ("e" if s[i] != "e" else "a") + s[i + 1:]

def main():
    rnd = random.Random(7); graphs = sys.argv[1:]
    all_syms = {g: load(g) for g in graphs}
    for g in graphs:
        syms = all_syms[g]; m = Matcher(syms)
        pool = [s for s in syms if len(s[2]) >= 6]; rnd.shuffle(pool); pool = pool[:250]
        others = [s[2] for og in graphs if og != g for s in all_syms[og] if len(s[2]) >= 6]; rnd.shuffle(others)
        negs = [n for n in others[:400] if n not in m.names][:200]
        kinds = {"exact name": lambda s: s[2], "one typo": lambda s: typo(s[2], rnd),
                 "two words of it": lambda s: " ".join(words(s[2])[:2]) if len(words(s[2])) >= 2 else s[2],
                 "wrong case": lambda s: s[2].lower(), "prefix only": lambda s: s[2][:max(4, len(s[2]) // 2)]}
        print(f"\n== {Path(g).name}: {len(syms)} symbols, {len(m.names)} distinct names; {sum(1 for n in m.names if sum(1 for s in syms if s[2]==n)>1)} names shared by several symbols")
        print(f"{'query kind':18s} " + " ".join(f"{t:>14s}" for t in ("A exact", "B +affix", "C +words", "D +edit sim")) + "   (success @1 / @3 / @8)")
        for kname, fn in kinds.items():
            row = []
            for tier in range(4):
                ok = collections.Counter()
                for s in pool:
                    q = fn(s); r = m.rank(q, tier)
                    for k in (1, 3, 8):
                        if any(m.names[i] == s[2] for i, _ in r[:k]): ok[k] += 1
                row.append("/".join(f"{100 * ok[k] // len(pool):3d}" for k in (1, 3, 8)))
            print(f"{kname:18s} " + " ".join(f"{x:>14s}" for x in row))
        for tier, thr in ((2, 40), (3, 40), (3, 50), (3, 55)):
            fa = sum(1 for n in negs if (r := m.rank(n, tier)) and r[0][1] >= thr)
            print(f"false accepts on {len(negs)} names that do not exist: tier {'ABCD'[tier]} threshold {thr}: {100 * fa // len(negs)}%")
main()
