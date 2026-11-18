#!/usr/bin/env python3
"""Score one arm's C/C++ graph against compiler truth (truth_clang.py) and against the owner's constraints.

  quality.py WORKTREE REPO_DIR TRUTH.json [--examples]    ->  JSON on stdout

Runs WORKTREE's own devkb code on REPO_DIR. Symbols are matched to truth definitions by (file, qualified name), then by
line containment, so an arm's choice of line_start semantics or overload handling does not matter.
Reports: symbol recall; call-edge precision (correct / (correct + wrong), unmapped ends excluded and counted),
call-edge recall against the truth, build seconds; and the honesty rate: of the linked edges, how many are wrong.

SPEC-DKB-004 F1: the truth keeps recursive calls; a devkb edge in or into a file the truth could not compile
(`not_compiled`) is `edges_not_measured`, neither correct nor wrong; vendored files (the truth's `vendored` list, else the
corpus file's) are excluded from the score on both sides (`edges_vendored_excluded`, `symbols_vendored_excluded`).
Importable: `run_devkb`, `score`, `classify_edges` (adjudicate.py uses them).
"""
import collections, json, os, subprocess, sys, textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CORPUS, is_vendored, vendored_prefixes

CODE = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    from devkb import build_symbols
    t = time.time(); g = build_symbols.extract(Path(sys.argv[1])); dt = time.time() - t
    nodes = {n.uid: n for n in g.nodes("Symbol")}
    cpp = (".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp")
    syms = [{"uid": u, "key": n.natural_key, "kind": n.props.get("kind"), "ls": n.props.get("line_start"), "le": n.props.get("line_end"), "lang": n.props.get("language")}
            for u, n in nodes.items() if n.natural_key.split("::")[0].lower().endswith(cpp)]
    edges = [[e.from_uid, e.to_uid, e.confidence, e.source, e.evidence_ref] for e in g.edges("CALLS") if e.from_uid in nodes and nodes[e.from_uid].natural_key.split("::")[0].lower().endswith(cpp)]
    print(json.dumps({"secs": dt, "syms": syms, "edges": edges}))
''')


def run_devkb(worktree, repo):
    """devkb's own symbols and CALLS edges for `repo`, from the code in `worktree`: {"secs", "syms", "edges": [[from, to, conf, source, evidence]]}."""
    p = subprocess.run([sys.executable, "-P", "-W", "ignore", "-c", CODE, str(Path(repo).resolve())], cwd="/", capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(Path(worktree).resolve())), timeout=1800)
    if p.returncode:
        raise RuntimeError(p.stderr[-400:])
    return json.loads(p.stdout.splitlines()[-1])


def file_of(key):
    return key.split("::", 1)[0]


def truth_index(truth):
    by_name = collections.defaultdict(set)     # (file, qn) -> {usr}
    by_file = collections.defaultdict(list)    # file -> [(start, end, usr)]
    for usr, (f, s, e, qn) in truth["defs"].items():
        by_name[(f, qn)].add(usr)
        by_file[f].append((s, e, usr))
    return by_name, by_file


def scope(truth, repo_name, corpus=CORPUS):
    """(vendored prefixes, not-compiled file set) this truth was built with; the corpus file fills in a truth older than F1."""
    vendored = list(truth.get("vendored") or vendored_prefixes(repo_name, corpus))
    return vendored, set(truth.get("not_compiled", []))


def classify_edges(out, truth, repo_name, corpus=CORPUS):
    """Every devkb CALLS edge with its place in the score. Returns (edges, mapping, in_scope_syms) where each edge is
    {"from","to","source","evidence","status"} and status is one of
      vendored      caller or callee file is vendored: not scored
      not_measured  caller or callee file is one the truth could not compile: not scored, not wrong
      unmapped      an end has no truth definition: not scored (adjudicate.py judges these by hand)
      correct       truth has this (caller, callee) edge
      wrong         both ends are truth definitions and the truth has no such edge
    """
    vendored, not_compiled = scope(truth, repo_name, corpus)
    by_name, by_file = truth_index(truth)
    truth_edges = {(a, b) for a, b in truth["edges"]}
    mapping = {}
    for s in out["syms"]:
        if s["kind"] not in ("function", "method"):
            continue
        f, qn = s["key"].split("::", 1)
        if is_vendored(f, vendored) or f in not_compiled:
            continue
        hit = set(by_name.get((f, qn), ()))
        if not hit and s["ls"]:
            hit = {u for st, en, u in by_file.get(f, []) if st <= s["ls"] <= en}
        if hit:
            mapping[s["uid"]] = hit
    key_of = {x["uid"]: x["key"] for x in out["syms"]}
    edges = []
    for a, b, _conf, src, ev in out["edges"]:
        fa, fb = file_of(key_of.get(a, "")), file_of(key_of.get(b, ""))
        if is_vendored(fa, vendored) or is_vendored(fb, vendored):
            status = "vendored"
        elif fa in not_compiled or fb in not_compiled:
            status = "not_measured"
        elif not mapping.get(a) or not mapping.get(b):
            status = "unmapped"
        elif any((x, y) in truth_edges for x in mapping[a] for y in mapping[b]):
            status = "correct"
        else:
            status = "wrong"
        edges.append({"from": a, "to": b, "source": src, "evidence": ev, "status": status})
    return edges, mapping, (vendored, not_compiled)


def score(out, truth, repo_name, examples=False, corpus=CORPUS):
    """The quality report (a dict) for devkb output `out` against `truth`."""
    defs = truth["defs"]
    truth_edges = {(a, b) for a, b in truth["edges"]}
    edges, mapping, (vendored, not_compiled) = classify_edges(out, truth, repo_name, corpus)
    callable_kinds = ("function", "method")
    key_of = {x["uid"]: x["key"] for x in out["syms"]}
    lang_of = {x["uid"]: x["lang"] for x in out["syms"]}
    matched_defs = set().union(*mapping.values()) if mapping else set()
    unmapped_syms = vendored_syms = not_compiled_syms = 0
    for s in out["syms"]:
        if s["kind"] not in callable_kinds:
            continue
        f = file_of(s["key"])
        if is_vendored(f, vendored):
            vendored_syms += 1
        elif f in not_compiled:
            not_compiled_syms += 1
        elif s["uid"] not in mapping:
            unmapped_syms += 1
    src_stat = collections.defaultdict(lambda: {"edges": 0, "correct": 0, "wrong": 0, "unmapped": 0, "found": set()})
    lang_stat = collections.defaultdict(lambda: {"edges": 0, "correct": 0, "wrong": 0, "unmapped": 0})
    cross_counts = collections.Counter()
    status_count = collections.Counter(e["status"] for e in edges)
    found, wrong_examples = set(), []
    wrong_by_source, ok_by_source = collections.Counter(), collections.Counter()
    for e in edges:
        a, b, src, status = e["from"], e["to"], e["source"], e["status"]
        if status in ("vendored", "not_measured"):
            continue
        lg = lang_of.get(a) or "?"
        src_stat[src]["edges"] += 1
        lang_stat[lg]["edges"] += 1
        if src == "extern-c":
            cross_counts[f"{lang_of.get(a)}->{lang_of.get(b)}"] += 1
        if status == "unmapped":
            src_stat[src]["unmapped"] += 1
            lang_stat[lg]["unmapped"] += 1
        elif status == "correct":
            hit = {(x, y) for x in mapping[a] for y in mapping[b] if (x, y) in truth_edges}
            ok_by_source[src] += 1
            found |= hit
            src_stat[src]["correct"] += 1
            src_stat[src]["found"] |= hit
            lang_stat[lg]["correct"] += 1
        else:
            wrong_by_source[src] += 1
            src_stat[src]["wrong"] += 1
            lang_stat[lg]["wrong"] += 1
            if len(wrong_examples) < 400:
                wrong_examples.append([key_of.get(a), key_of.get(b), src])
    correct, wrong = status_count["correct"], status_count["wrong"]
    macro_only = {tuple(e) for e in truth.get("macro_only", [])}

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
    is_c = lambda usr: defs[usr][0].lower().endswith((".c",))
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
        "repo": repo_name, "build_secs": round(out["secs"], 1),
        "truth_defs": len(defs), "truth_edges": len(truth_edges), "truth_recursive_edges": sum(1 for a, b in truth_edges if a == b),
        "truth_edges_only_via_macro": len(macro_only),
        "symbol_recall": round(len(matched_defs) / max(1, len(defs)), 3),
        "symbol_recall_by_name": round(len({(defs[u][0], defs[u][3]) for u in matched_defs}) / max(1, len({(d[0], d[3]) for d in defs.values()})), 3),
        "devkb_callable_symbols": total_syms, "symbols_without_a_truth_definition": unmapped_syms,
        "symbols_vendored_excluded": vendored_syms, "symbols_not_measured": not_compiled_syms,
        "not_compiled_files": sorted(not_compiled), "vendored_prefixes": vendored,
        "edges_linked": len(out["edges"]), "edges_scored": correct + wrong, "edges_unmapped": status_count["unmapped"],
        "edges_not_measured": status_count["not_measured"], "edges_vendored_excluded": status_count["vendored"],
        "edge_precision": round(correct / max(1, correct + wrong), 3),
        "edge_recall": round(len(found) / max(1, len(truth_edges)), 3),
        "wrong_edges": wrong, "missed_truth_edges_by_callee_kind": dict(missed), "correct_by_source": dict(ok_by_source), "wrong_by_source": dict(wrong_by_source),
        "by_source": by_source, "by_language": by_language, "extern_c_by_language": dict(cross_counts),
    }
    if examples:
        res["wrong_examples"] = wrong_examples
    return res, by_source


def main(argv):
    W, REPO, TRUTH = Path(argv[0]).resolve(), Path(argv[1]).resolve(), json.load(open(argv[2]))
    try:
        out = run_devkb(W, REPO)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)})); return 0
    res, by_source = score(out, TRUTH, REPO.name, examples="--examples" in argv)
    print(json.dumps(res))
    # SPEC-DKB-002 story 3: the committed floor of the `extern-c` precision (devkb/bench/cpp_corpus.json); below it, exit 1
    floor = json.loads(CORPUS.read_text()).get("floors", {}).get(REPO.name, {}).get("by_source", {}).get("extern-c", {}).get("precision") if CORPUS.exists() else None
    got = by_source.get("extern-c")
    if floor is not None and got is not None and got["precision"] < floor:
        print(f"FAIL extern-c precision {got['precision']} is below the committed floor {floor}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
