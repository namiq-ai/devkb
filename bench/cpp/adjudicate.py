#!/usr/bin/env python3
"""Adjudicated precision of devkb's C/C++ CALLS edges: a seeded sample, hand verdicts, a 95% interval (SPEC-DKB-004 F1).

  adjudicate.py draw WORKTREE REPO_DIR TRUTH.json SAMPLE.jsonl [--n 100] [--seed 117] [--force]
  adjudicate.py show SAMPLE.jsonl --repo REPO_DIR [--pending|--all] [--ids 3,7]
  adjudicate.py judge SAMPLE.jsonl ID=correct|wrong[:note] ...
  adjudicate.py report SAMPLE.jsonl [SAMPLE.jsonl ...] [--markdown]

`draw` runs WORKTREE's devkb on REPO_DIR and takes the edges quality.py puts in scope (not vendored, not in a file the
truth could not compile) in a fixed order, then `random.Random(seed).sample`s n of them. Each sampled edge is
  - truth     the compiler truth has this (caller, callee) edge: recorded `correct`, by "truth";
  - wrong     both ends are truth definitions and the truth has no such edge: a person judges it;
  - unmapped  an end has no truth definition: a person judges it.
A person judges an edge **correct** when the call in the caller's body can only mean that definition (C++ name lookup:
qualified name, the caller's class and its bases, the receiver's type, namespace), and **wrong** when it can mean
another function, the callee is called nowhere in the body, or the call is not a call. Recursion and calls the compiler
cannot see (uninstantiated templates, macros) are judged on the source like any other. `show` prints what is needed
(the caller's lines that name the callee, the callee's definition, what the truth links from the caller under that name);
`judge` writes the verdict into the JSONL. `report` refuses a sample with a pending edge and prints precision
(truth-confirmed + hand-correct) / n with a Wilson 95% interval, by repository and by edge source.
The first line of a sample file is {"meta": ...}; the others are the sampled edges.
"""
import collections, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import wilson


def _lines(repo, rel, cache={}):
    if (repo, rel) not in cache:
        try:
            cache[(repo, rel)] = (Path(repo) / rel).read_text(errors="replace").splitlines()
        except OSError:
            cache[(repo, rel)] = []
    return cache[(repo, rel)]


def draw(worktree, repo, truth_path, out_path, n=100, seed=117, force=False):
    import quality
    out_path = Path(out_path)
    if out_path.exists() and not force:
        raise SystemExit(f"{out_path} exists: it holds verdicts; pass --force to redraw")
    repo = Path(repo).resolve()
    truth = json.load(open(truth_path))
    out = quality.run_devkb(worktree, repo)
    edges, mapping, (vendored, not_compiled) = quality.classify_edges(out, truth, repo.name)
    syms = {s["uid"]: s for s in out["syms"]}
    by_edge = collections.defaultdict(set)                # truth caller usr -> callee usrs
    for a, b in truth["edges"]:
        by_edge[a].add(b)
    frame = []
    for e in edges:
        if e["status"] in ("correct", "wrong", "unmapped"):
            frame.append(e)
    key = lambda e: (syms[e["from"]]["key"], syms[e["to"]]["key"])
    frame.sort(key=key)
    picked = sorted(random.Random(seed).sample(range(len(frame)), min(n, len(frame))))
    rows = []
    for i, ix in enumerate(picked, 1):
        e = frame[ix]
        a, b = syms[e["from"]], syms[e["to"]]
        last = b["key"].split("::", 1)[1].rsplit(".", 1)[-1]
        same_name = sorted({truth["defs"][t][3] for u in mapping.get(e["from"], ()) for t in by_edge[u]
                            if truth["defs"][t][3].rsplit(".", 1)[-1] == last})
        row = {"id": i, "caller": a["key"], "callee": b["key"], "source": e["source"], "status": {"correct": "truth"}.get(e["status"], e["status"]),
               "caller_span": [a["ls"], a["le"]], "callee_line": b["ls"], "truth_same_name_from_caller": same_name,
               "verdict": "correct" if e["status"] == "correct" else None, "by": "truth" if e["status"] == "correct" else None, "note": ""}
        rows.append(row)
    status_n = collections.Counter(e["status"] for e in frame)
    meta = {"repo": repo.name, "seed": seed, "n": len(rows), "frame": len(frame), "frame_by_status": dict(status_n),
            "excluded": {"vendored": vendored, "not_compiled": sorted(not_compiled),
                         "edges_vendored": sum(1 for e in edges if e["status"] == "vendored"),
                         "edges_not_measured": sum(1 for e in edges if e["status"] == "not_measured")}}
    with open(out_path, "w") as f:
        f.write(json.dumps({"meta": meta}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    pending = sum(1 for r in rows if r["verdict"] is None)
    print(f"{repo.name}: frame {len(frame)} edges {dict(status_n)}; sampled {len(rows)} (seed {seed}); {pending} to judge by hand -> {out_path}")


def load(path):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    return recs[0]["meta"], recs[1:]


def save(path, meta, rows):
    with open(path, "w") as f:
        f.write(json.dumps({"meta": meta}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")


def show(path, repo, which="pending", ids=None):
    meta, rows = load(path)
    for r in rows:
        if ids and r["id"] not in ids:
            continue
        if not ids and which == "pending" and r["verdict"] is not None:
            continue
        f, qn = r["caller"].split("::", 1)
        tf, tqn = r["callee"].split("::", 1)
        name = tqn.rsplit(".", 1)[-1].lstrip("~")
        print(f"#{r['id']} [{r['source']}, {r['status']}] {qn} -> {tqn}   ({f} -> {tf})")
        ls, le = r["caller_span"]
        body = _lines(repo, f)
        hits = [(i, body[i - 1].strip()) for i in range(ls or 1, (le or ls or 1) + 1) if 0 < i <= len(body) and name in body[i - 1]]
        for i, t in hits[:8]:
            print(f"    call? {f}:{i}: {t[:150]}")
        if not hits:
            print(f"    call? no line of {f}:{ls}-{le} names '{name}'")
        d = _lines(repo, tf)
        if r["callee_line"] and 0 < r["callee_line"] <= len(d):
            print(f"    def   {tf}:{r['callee_line']}: {d[r['callee_line'] - 1].strip()[:150]}")
        if r["truth_same_name_from_caller"]:
            print(f"    truth links from this caller under that name: {', '.join(r['truth_same_name_from_caller'])}")
        if r["verdict"]:
            print(f"    verdict: {r['verdict']} ({r['by']}) {r['note']}")


def judge(path, items):
    meta, rows = load(path)
    by_id = {r["id"]: r for r in rows}
    for it in items:
        ident, _, rest = it.partition("=")
        verdict, _, note = rest.partition(":")
        if verdict not in ("correct", "wrong") or not ident.isdigit() or int(ident) not in by_id:
            raise SystemExit(f"bad verdict {it!r}: expected ID=correct|wrong[:note] with an ID in {path}")
        r = by_id[int(ident)]
        if r["by"] == "truth":
            raise SystemExit(f"#{ident} is confirmed by the compiler truth; it is not judged by hand")
        r.update(verdict=verdict, by="hand", note=note.strip())
    save(path, meta, rows)


def summarize(path):
    """Counts and the adjudicated precision of one sample file; raises if an edge has no verdict."""
    meta, rows = load(path)
    pending = [r["id"] for r in rows if r["verdict"] is None]
    if pending:
        raise SystemExit(f"{path}: {len(pending)} edges without a verdict (ids {pending[:10]}...)")
    n = len(rows)
    truth = sum(1 for r in rows if r["by"] == "truth")
    hand = [r for r in rows if r["by"] == "hand"]
    hand_ok = sum(1 for r in hand if r["verdict"] == "correct")
    k = truth + hand_ok
    lo, hi = wilson(k, n)
    by_source = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by_source[r["source"]][0] += 1
        by_source[r["source"]][1] += r["verdict"] == "correct"
    return {"repo": meta["repo"], "n": n, "frame": meta["frame"], "truth_confirmed": truth, "hand_judged": len(hand), "hand_correct": hand_ok,
            "hand_wrong": len(hand) - hand_ok, "correct": k, "precision": k / n if n else 0.0, "low": lo, "high": hi,
            "by_source": {s: {"n": v[0], "correct": v[1]} for s, v in sorted(by_source.items())}, "seed": meta["seed"],
            "frame_by_status": meta["frame_by_status"]}


def report(paths, markdown=False):
    sums = [summarize(p) for p in paths]
    if markdown:
        print("| Repository | In-scope edges | Sampled | Truth-confirmed | Judged by hand | of which correct | **Adjudicated precision** | 95% interval |")
        print("|---|---|---|---|---|---|---|---|")
        for s in sums:
            print(f"| {s['repo']} | {s['frame']:,} | {s['n']} | {s['truth_confirmed']} | {s['hand_judged']} | {s['hand_correct']} | "
                  f"**{s['precision']:.3f}** ({s['correct']}/{s['n']}) | {s['low']:.3f} to {s['high']:.3f} |")
        print()
        print("| Repository | " + " | ".join(sorted({x for s in sums for x in s["by_source"]})) + " |")
        srcs = sorted({x for s in sums for x in s["by_source"]})
        print("|---|" + "---|" * len(srcs))
        for s in sums:
            print(f"| {s['repo']} | " + " | ".join(f"{s['by_source'][x]['correct']}/{s['by_source'][x]['n']}" if x in s["by_source"] else "" for x in srcs) + " |")
    else:
        print(json.dumps(sums, indent=1))
    return sums


def main(argv):
    if not argv or argv[0] not in ("draw", "show", "judge", "report"):
        raise SystemExit(__doc__)
    cmd, rest = argv[0], argv[1:]
    opt = lambda name, default=None: rest[rest.index(name) + 1] if name in rest else default
    if cmd == "draw":
        draw(rest[0], rest[1], rest[2], rest[3], n=int(opt("--n", 100)), seed=int(opt("--seed", 117)), force="--force" in rest)
    elif cmd == "show":
        ids = {int(x) for x in opt("--ids", "").split(",") if x}
        show(rest[0], opt("--repo", "."), "all" if "--all" in rest else "pending", ids)
    elif cmd == "judge":
        judge(rest[0], rest[1:])
    else:
        report([a for a in rest if not a.startswith("--")], "--markdown" in rest)


if __name__ == "__main__":
    main(sys.argv[1:])
