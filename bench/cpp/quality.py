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
    syms = [{"uid": u, "key": n.natural_key, "kind": n.props.get("kind"), "ls": n.props.get("line_start"), "le": n.props.get("line_end"), "lang": n.props.get("language")}
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
lang_of = {x["uid"]: x["lang"] for x in out["syms"]}
src_stat = collections.defaultdict(lambda: {"edges": 0, "correct": 0, "wrong": 0, "unmapped": 0, "found": set()})   # by edge source
lang_stat = collections.defaultdict(lambda: {"edges": 0, "correct": 0, "wrong": 0, "unmapped": 0})                 # by caller language
cross_counts = collections.Counter()      # extern-c edges by "caller language->callee language"
found = set()
wrong_examples = []
wrong_by_source = collections.Counter()
ok_by_source = collections.Counter()
key_of = {x["uid"]: x["key"] for x in out["syms"]}
for a, b, conf, src in out["edges"]:
    ta, tb = mapping.get(a), mapping.get(b)
    for st in (src_stat[src], lang_stat[lang_of.get(a) or "?"]):
        st["edges"] += 1
    if src == "extern-c":
        cross_counts[f"{lang_of.get(a)}->{lang_of.get(b)}"] += 1
    if not ta or not tb:
        skipped += 1
        src_stat[src]["unmapped"] += 1
        lang_stat[lang_of.get(a) or "?"]["unmapped"] += 1
        continue
    hit = {(x, y) for x in ta for y in tb if (x, y) in truth_edges}
    if hit:
        correct += 1
        ok_by_source[src] += 1
        found |= hit
        src_stat[src]["correct"] += 1
        src_stat[src]["found"] |= hit
        lang_stat[lang_of.get(a) or "?"]["correct"] += 1
    else:
        wrong += 1
        wrong_by_source[src] += 1
        src_stat[src]["wrong"] += 1
        lang_stat[lang_of.get(a) or "?"]["wrong"] += 1
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
C_EXT = (".c",)
def is_c(usr): return defs[usr][0].lower().endswith(C_EXT)
cross_truth = {(a, b) for a, b in truth_edges if is_c(a) != is_c(b)}
by_source = {}
for src, st in src_stat.items():
    scored = st["correct"] + st["wrong"]
    by_source[src] = {"edges": st["edges"], "precision": round(st["correct"] / scored, 3) if scored else 1.0, "unmapped": st["unmapped"],
                      "recall": round(len(st["found"] & cross_truth) / max(1, len(cross_truth)), 3) if src == "extern-c" else None}
by_language = {}
for lang, st in lang_stat.items():
    scored = st["correct"] + st["wrong"]
    by_language[lang] = {"edges": st["edges"], "precision": round(st["correct"] / scored, 3) if scored else 1.0, "unmapped": st["unmapped"]}
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
    "by_source": by_source, "by_language": by_language, "extern_c_by_language": dict(cross_counts),
}
if "--examples" in sys.argv:
    res["wrong_examples"] = wrong_examples
print(json.dumps(res))
# SPEC-DKB-002 story 3: the committed floor of the `extern-c` precision (devkb/bench/cpp_corpus.json); below it, exit 1
corpus = Path(__file__).resolve().parents[2] / "devkb" / "bench" / "cpp_corpus.json"
floor = json.loads(corpus.read_text()).get("floors", {}).get(REPO.name, {}).get("by_source", {}).get("extern-c", {}).get("precision") if corpus.exists() else None
got = by_source.get("extern-c")
if floor is not None and got is not None and got["precision"] < floor:
    print(f"FAIL extern-c precision {got['precision']} is below the committed floor {floor}", file=sys.stderr)
    sys.exit(1)
