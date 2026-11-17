#!/usr/bin/env python3
"""The graph of each repository, measured: nodes and edges by type, symbols by language, size on disk and build time.

  graph_info.py CODE_DIR LABEL OUT.json NAME=PATH [NAME=PATH ...]

Builds with the devkb checkout in CODE_DIR (`devkb build --project PATH`, the graph goes to PATH/.devkb and is removed afterwards) and
writes one JSON record per repository, with the commit the repository was at. A release is compared with a stored baseline by
`graph_compare.py`; the baseline of 2026-11-17 is in bench/results/2026-11-17-graph-baseline/ and docs/analysis/graph-baseline.md.
Run one repository after another on a quiet machine; set PERF_PYTHON to the interpreter."""
import collections, json, os, shutil, subprocess, sys, time
from pathlib import Path

code, label, out = sys.argv[1:4]
py = os.environ.get("PERF_PYTHON", sys.executable)
prev = json.load(open(out)) if Path(out).exists() else {"repos": {}}      # a later run adds to (or replaces entries of) an earlier file
res = {"label": label, "code": subprocess.run(["git", "rev-parse", "HEAD"], cwd=code, capture_output=True, text=True).stdout.strip(),
       "python": subprocess.run([py, "--version"], capture_output=True, text=True).stdout.strip(), "repos": prev["repos"]}
for spec in sys.argv[4:]:
    name, path = spec.split("=", 1)
    shutil.rmtree(Path(path) / ".devkb", ignore_errors=True)
    t = time.time()
    env = dict(os.environ, PYTHONPATH=code)
    cmd = lambda mod, *extra: [py, "-P", "-W", "ignore", "-m", mod, "--project", path, *extra]
    if (Path(path) / "devkb" / "cli.py").exists():     # devkb's own repository carries its own code: only `devkb.build` takes the flag
        steps = [cmd("devkb.build_symbols"), cmd("devkb.build", "--allow-foreign-checkout")]
    else:
        steps = [cmd("devkb.build_symbols"), cmd("devkb.build")]
    for step in steps:
        r = subprocess.run(step, env=env, capture_output=True, text=True)
        if r.returncode:
            break
    secs = time.time() - t; d = Path(path) / ".devkb"
    if not (d / "nodes.jsonl").exists():
        print("build failed:", name, r.stderr[-300:], file=sys.stderr); continue
    nt, ev, lang, kinds = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for l in open(d / "nodes.jsonl"):
        n = json.loads(l); nt[n["type"]] += 1
        if n["type"] == "Symbol":
            p = n.get("properties", {})
            lang[p.get("language") or ("python" if n["natural_key"].split("::")[0].endswith(".py") else "none")] += 1
            kinds[p.get("kind", "?")] += 1
    for l in open(d / "edges.jsonl"):
        ev[json.loads(l)["verb"]] += 1
    git = lambda *a: subprocess.run(["git", *a], cwd=path, capture_output=True, text=True).stdout.strip()
    res["repos"][name] = dict(commit=git("rev-parse", "HEAD"), commits_in_clone=int(git("rev-list", "--count", "HEAD") or 0),
                              files=len(git("ls-files").splitlines()), build_secs=round(secs, 1),
                              graph_mb=round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6, 1),
                              nodes=sum(nt.values()), edges=sum(ev.values()), node_types=dict(nt), edge_verbs=dict(ev),
                              symbol_languages=dict(lang), symbol_kinds=dict(kinds))
    print(name, res["repos"][name]["nodes"], res["repos"][name]["edges"], res["repos"][name]["build_secs"], flush=True)
    shutil.rmtree(d, ignore_errors=True)
    json.dump(res, open(out, "w"), indent=1)
