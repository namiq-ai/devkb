#!/usr/bin/env python3
"""Score one arm's C/C++ graph against compiler truth (truth_clang.py) and against the owner's constraints.

  quality.py WORKTREE REPO_DIR TRUTH.json     ->  JSON on stdout

Runs WORKTREE's own devkb code on REPO_DIR. Symbols are matched to truth definitions by (file, qualified name), then by
line containment, so an arm's choice of line_start semantics or overload handling does not matter.
Reports: symbol recall; call-edge precision (correct / (correct + wrong), unmapped ends excluded and counted),
call-edge recall against the truth, build seconds; and the honesty rate: of the linked edges, how many are wrong.
"""
import collections, json, os, subprocess, sys, textwrap
from pathlib import Path

W, REPO, TRUTH = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), json.load(open(sys.argv[3]))
CODE = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    from devkb import build_symbols
    t = time.time(); g = build_symbols.extract(Path(sys.argv[1])); dt = time.time() - t
    nodes = {n.uid: n for n in g.nodes("Symbol")}
    cpp = (".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp")
    syms = [{"uid": u, "key": n.natural_key, "kind": n.props.get("kind"), "ls": n.props.get("line_start"), "le": n.props.get("line_end")}
            for u, n in nodes.items() if n.natural_key.split("::")[0].lower().endswith(cpp)]
    edges = [[e.from_uid, e.to_uid, e.confidence, e.source] for e in g.edges("CALLS") if e.from_uid in nodes and nodes[e.from_uid].natural_key.split("::")[0].lower().endswith(cpp)]
    print(json.dumps({"secs": dt, "syms": syms, "edges": edges}))
''')
p = subprocess.run([sys.executable, "-P", "-W", "ignore", "-c", CODE, str(REPO)], cwd="/", capture_output=True, text=True,
                   env=dict(os.environ, PYTHONPATH=str(W)), timeout=1800)
if p.returncode:
    print(json.dumps({"error": p.stderr[-400:]})); sys.exit(0)
out = json.loads(p.stdout.splitlines()[-1])

defs = TRUTH["defs"]                       # usr -> [file, start, end, qn]
by_name = collections.defaultdict(set)     # (file, qn) -> {usr}
by_file = collections.defaultdict(list)    # file -> [(start, end, usr)]
for usr, (f, s, e, qn) in defs.items():
    by_name[(f, qn)].add(usr)
    by_file[f].append((s, e, usr))
truth_edges = {(a, b) for a, b in TRUTH["edges"]}
callable_kinds = ("function", "method")
mapping, unmapped = {}, 0                  # devkb uid -> {usr}
matched_defs = set()
for s in out["syms"]:
    if s["kind"] not in callable_kinds:
        continue
    f, qn = s["key"].split("::", 1)
    hit = set(by_name.get((f, qn), ()))
    if not hit and s["ls"]:
        hit = {u for st, en, u in by_file.get(f, []) if st <= s["ls"] <= en}
    if hit:
        mapping[s["uid"]] = hit
        matched_defs |= hit
    else:
        unmapped += 1
correct = wrong = skipped = 0
found = set()
wrong_examples = []
wrong_by_source = collections.Counter()
ok_by_source = collections.Counter()
key_of = {x["uid"]: x["key"] for x in out["syms"]}
for a, b, conf, src in out["edges"]:
    ta, tb = mapping.get(a), mapping.get(b)
    if not ta or not tb:
        skipped += 1
        continue
    hit = {(x, y) for x in ta for y in tb if (x, y) in truth_edges}
    if hit:
        correct += 1
        ok_by_source[src] += 1
        found |= hit
    else:
        wrong += 1
        wrong_by_source[src] += 1
        if len(wrong_examples) < 400:
            wrong_examples.append([key_of.get(a), key_of.get(b), src])
macro_only = {tuple(e) for e in TRUTH.get("macro_only", [])}
def classify(callee_qn, same_file):
    last = callee_qn.rsplit(".", 1)[-1]; parts = callee_qn.split(".")
    if last.startswith("~"): return "destructor"
    if last.startswith("operator"): return "operator"
    if len(parts) >= 2 and parts[-2] == last: return "constructor"
    if len(parts) >= 2 and parts[-2][:1].isupper(): return "method (class member)"
    return "free function" + (" (same file)" if same_file else " (other file)")
missed = collections.Counter()
for a, b in truth_edges - found:
    missed["call produced by a macro expansion (invisible to a text scan)" if (a, b) in macro_only else classify(defs[b][3], defs[a][0] == defs[b][0])] += 1
total_syms = len([s for s in out["syms"] if s["kind"] in callable_kinds])
res = {
    "repo": REPO.name, "build_secs": round(out["secs"], 1),
    "truth_defs": len(defs), "truth_edges": len(truth_edges), "truth_edges_only_via_macro": len(macro_only),
    "symbol_recall": round(len(matched_defs) / max(1, len(defs)), 3),
    "devkb_callable_symbols": total_syms, "symbols_without_a_truth_definition": unmapped,
    "edges_linked": len(out["edges"]), "edges_scored": correct + wrong, "edges_unmapped": skipped,
    "edge_precision": round(correct / max(1, correct + wrong), 3),
    "edge_recall": round(len(found) / max(1, len(truth_edges)), 3),
    "wrong_edges": wrong, "missed_truth_edges_by_callee_kind": dict(missed), "correct_by_source": dict(ok_by_source), "wrong_by_source": dict(wrong_by_source),
}
if "--examples" in sys.argv:
    res["wrong_examples"] = wrong_examples
print(json.dumps(res))
