#!/usr/bin/env python3
"""What a devkb graph is made of, and what it costs (ODSF-314).

Per verb: count, share of all edges, fan-out per source node (p50/p99/max), source mix, confidence spread, dangling
edges, the share that touches a generated path, and whether any process-API tool reads it. Per node type: count,
orphans, generated-path share. Size: JSONL and cache bytes, cold load and warm query time.

  python3 devkb/audit.py --project OCO                     # the project's live .devkb
  python3 devkb/audit.py --project OCO --dir <snapshot>    # any built graph directory
  python3 devkb/audit.py --project OCO --json OUT.json
  python3 devkb/audit.py --project OCO --check             # exit 1 when a floor in FLOORS fails
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.model import VERBS  # noqa: E402

HERE = Path(__file__).resolve().parent
GENERATED = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|Cargo\.lock)$|"
                       r"\.min\.(js|css)$|(^|/)(dist|build|node_modules|__pycache__|\.next[^/]*)/")
# Floors a healthy graph keeps; set from the measured values in docs/graph-audit-odsf314.md.
FLOORS = {"max_low_value_share": 0.60, "max_generated_edge_share": 0.02, "max_dangling_share": 0.001}  # OCO after ODSF-314: 0.56, 0.000, 0.00005
LOW_VALUE = ("TOUCHES", "SIMILAR_TO", "IN_REPO", "GROUPS")


def _pct(xs: list[int], q: float) -> int:
    if not xs:
        return 0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))]


def tool_reads() -> dict[str, int]:
    text = "".join((HERE / f).read_text() for f in ("process_api.py", "packs.py", "service.py") if (HERE / f).exists())
    return {v: len(re.findall(r'"' + v + r'"', text)) for v in VERBS}


def audit(devkb_dir: Path) -> dict:
    nodes: dict[str, tuple[str, str]] = {}
    for line in (devkb_dir / "nodes.jsonl").read_text().splitlines():
        if line:
            n = json.loads(line)
            nodes[n["uid"]] = (n["type"], n["natural_key"])
    degree: collections.Counter = collections.Counter()
    verb = collections.Counter()
    fan: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    src: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    conf: dict[str, list[float]] = collections.defaultdict(list)
    pairs: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    dangling, generated = collections.Counter(), collections.Counter()
    for line in (devkb_dir / "edges.jsonl").read_text().splitlines():
        if not line:
            continue
        e = json.loads(line)
        v, a, b = e["verb"], nodes.get(e["from_uid"]), nodes.get(e["to_uid"])
        verb[v] += 1
        p = e.get("properties") or {}
        src[v][str(p.get("source", "?")).split(":")[-1]] += 1
        conf[v].append(float(p.get("confidence") or 0))
        if a is None or b is None:
            dangling[v] += 1
            continue
        degree[e["from_uid"]] += 1
        degree[e["to_uid"]] += 1
        fan[v][e["from_uid"]] += 1
        pairs[v][f"{a[0]}->{b[0]}"] += 1
        if GENERATED.search(a[1].split("::")[0]) or GENERATED.search(b[1].split("::")[0]):
            generated[v] += 1
    total = sum(verb.values()) or 1
    reads = tool_reads()
    verbs = {}
    for v in sorted(verb, key=lambda x: -verb[x]):
        fo = list(fan[v].values())
        cs = conf[v]
        verbs[v] = {"n": verb[v], "share": round(verb[v] / total, 4), "pairs": dict(pairs[v].most_common(3)),
                    "fanout_p50": _pct(fo, 0.5), "fanout_p99": _pct(fo, 0.99), "fanout_max": max(fo, default=0),
                    "sources": dict(src[v].most_common(4)), "conf_min": round(min(cs), 2), "conf_max": round(max(cs), 2),
                    "conf_distinct": len({round(c, 2) for c in cs}), "dangling": dangling[v], "generated": generated[v],
                    "tool_reads": reads.get(v, 0)}
    types = collections.Counter(t for t, _ in nodes.values())
    orphans = collections.Counter(nodes[u][0] for u in nodes if not degree[u])
    gen_nodes = collections.Counter(t for u, (t, k) in nodes.items() if GENERATED.search(k.split("::")[0]))
    size = {name: (devkb_dir / name).stat().st_size for name in ("nodes.jsonl", "edges.jsonl", ".process-index.pkl")
            if (devkb_dir / name).exists()}
    return {"dir": str(devkb_dir), "nodes": len(nodes), "edges": total, "verbs": verbs,
            "types": {t: {"n": n, "orphans": orphans[t], "generated": gen_nodes[t]} for t, n in types.most_common()},
            "unused_verbs": [v for v in VERBS if v not in verb], "bytes": size,
            "low_value_share": round(sum(verb[v] for v in LOW_VALUE) / total, 4),
            "generated_edge_share": round(sum(generated.values()) / total, 4),
            "dangling_share": round(sum(dangling.values()) / total, 5)}


def timing(code: str, devkb_dir: Path) -> dict:
    from devkb import service  # noqa: PLC0415
    from devkb.process_api import ProcessAPI  # noqa: PLC0415
    cache = devkb_dir / service.CACHE_NAME
    if cache.exists():
        cache.unlink()
    t0 = time.perf_counter()
    api = ProcessAPI(code, devkb_dir=devkb_dir, telemetry=False)
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    ProcessAPI(code, devkb_dir=devkb_dir, telemetry=False)
    warm_load = time.perf_counter() - t0
    sym = max((v[0] for v in api.idx.short.values() if len(v) == 1), key=lambda s: len(api.idx.sources("CALLS", s)), default=None)
    samples = []
    for _ in range(20):
        t0 = time.perf_counter()
        api.call("callers", symbol=api.idx.keys[sym], depth=2)
        samples.append((time.perf_counter() - t0) * 1000)
    return {"cold_build_s": round(cold, 2), "cached_load_s": round(warm_load, 2),
            "callers_p50_ms": round(statistics.median(samples), 2), "cache_bytes": cache.stat().st_size if cache.exists() else 0}


def render(r: dict) -> str:
    lines = [f"Graph `{r['dir']}`: {r['nodes']:,} nodes, {r['edges']:,} edges; low-value verbs {r['low_value_share']:.0%} of edges, "
             f"generated paths {r['generated_edge_share']:.1%}, dangling {r['dangling_share']:.3%}.", "",
             "| Verb | Edges | Share | Fan-out p50/p99/max | Confidence (distinct) | Generated | Tool reads | Main source |",
             "|---|---|---|---|---|---|---|---|"]
    for v, s in r["verbs"].items():
        lines.append(f"| `{v}` | {s['n']:,} | {s['share']:.1%} | {s['fanout_p50']}/{s['fanout_p99']}/{s['fanout_max']} | "
                     f"{s['conf_min']}–{s['conf_max']} ({s['conf_distinct']}) | {s['generated']:,} | {s['tool_reads']} | "
                     f"{next(iter(s['sources']), '')} |")
    lines += ["", "Verbs with no edges: " + (", ".join(f"`{v}`" for v in r["unused_verbs"]) or "none"), "",
              "| Node type | Count | Orphans | Generated |", "|---|---|---|---|"]
    lines += [f"| `{t}` | {s['n']:,} | {s['orphans']:,} | {s['generated']:,} |" for t, s in r["types"].items()]
    if "timing" in r:
        t = r["timing"]
        lines += ["", f"Cold index build {t['cold_build_s']} s, cached load {t['cached_load_s']} s, `callers` p50 {t['callers_p50_ms']} ms, "
                  f"cache {t['cache_bytes'] / 1e6:.1f} MB; JSONL {sum(v for k, v in r['bytes'].items() if k.endswith('.jsonl')) / 1e6:.1f} MB."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="audit a devkb graph's content and cost")
    ap.add_argument("--project", required=True)
    ap.add_argument("--dir", help="a built graph directory (default: the project's .devkb)")
    ap.add_argument("--json")
    ap.add_argument("--timing", action="store_true", help="also measure index build and query time")
    ap.add_argument("--check", action="store_true")
    ns = ap.parse_args()
    if ns.dir:
        d = Path(ns.dir)
    else:
        from devkb.project_context import resolve  # noqa: PLC0415
        d = resolve(ns.project).devkb_dir
    from devkb.service import require_graph  # noqa: PLC0415
    require_graph(d, ns.project)                  # one line saying to build first, never a traceback (#293)
    r = audit(d)
    if ns.timing:
        r["timing"] = timing(ns.project, d)
    print(render(r))
    if ns.json:
        Path(ns.json).write_text(json.dumps(r, indent=1))
    if ns.check:
        bad = [k for k, v in (("max_low_value_share", r["low_value_share"]), ("max_generated_edge_share", r["generated_edge_share"]),
                              ("max_dangling_share", r["dangling_share"])) if v > FLOORS[k]]
        if bad:
            print("FLOOR FAILED: " + ", ".join(bad), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    from devkb.service import GraphNotBuilt

    try:
        sys.exit(main())
    except GraphNotBuilt as exc:                # `python -m devkb.audit` too: one line, exit 2, never a traceback (#293)
        print(f"devkb: {exc}", file=sys.stderr)
        sys.exit(2)
