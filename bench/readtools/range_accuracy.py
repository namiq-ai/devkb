#!/usr/bin/env python3
"""How accurate are the names and line ranges devkb stores for Symbols, per language, against an independent parse?

  range_accuracy.py REPO_DIR GRAPH_DIR LANG [--clang-truth FILE]

LANG: python | typescript | csharp | clang. Truth = tree-sitter definitions (python, typescript, csharp) or the libclang
truth from bench/cpp/truth_clang.py (clang). A graph Symbol is matched to a truth definition of the same short name in the
same file whose start is nearest, within WINDOW lines. Needs: pip install tree-sitter tree-sitter-python tree-sitter-typescript
tree-sitter-c-sharp. Output: JSON."""
import collections, json, sys
from pathlib import Path

WINDOW = 6
repo, graph, lang = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]

def load_symbols():
    out = collections.defaultdict(list)
    for l in open(graph / "nodes.jsonl"):
        n = json.loads(l)
        if n["type"] != "Symbol":
            continue
        f, q = n["natural_key"].split("::", 1)
        p = n["properties"]
        out[f].append(dict(q=q, short=q.rsplit(".", 1)[-1].split("::")[-1], kind=p.get("kind"), ls=p.get("line_start"), le=p.get("line_end")))
    return out

EXT = {"python": (".py",), "typescript": (".ts", ".tsx"), "csharp": (".cs",)}

def ts_defs(path, lang):
    import tree_sitter as ts
    if lang == "python":
        import tree_sitter_python as m; L = m.language()
    elif lang == "typescript":
        import tree_sitter_typescript as m; L = m.language_tsx() if str(path).endswith(".tsx") else m.language_typescript()
    else:
        import tree_sitter_c_sharp as m; L = m.language()
    parser = ts.Parser(ts.Language(L))
    src = path.read_bytes(); tree = parser.parse(src); out = []
    txt = lambda n: src[n.start_byte:n.end_byte].decode("utf8", "replace")
    def name_of(n):
        c = n.child_by_field_name("name")
        return txt(c) if c else None
    def visit(n):
        t = n.type; nm = None; srow = n.start_point[0] + 1; erow = n.end_point[0] + 1
        if lang == "python" and t in ("function_definition", "class_definition"):
            nm = name_of(n)
            if n.parent is not None and n.parent.type == "decorated_definition":
                srow_dec = n.parent.start_point[0] + 1
            else:
                srow_dec = srow
            out.append(dict(short=nm, start=srow, start_dec=srow_dec, end=erow, name_row=n.child_by_field_name("name").start_point[0] + 1))
        elif lang == "typescript":
            if t in ("function_declaration", "class_declaration", "abstract_class_declaration", "method_definition", "generator_function_declaration", "interface_declaration", "enum_declaration"):
                nm = name_of(n)
                if nm: out.append(dict(short=nm, start=srow, start_dec=srow, end=erow, name_row=n.child_by_field_name("name").start_point[0] + 1))
            elif t == "variable_declarator":
                v = n.child_by_field_name("value")
                if v is not None and v.type in ("arrow_function", "function_expression", "function"):
                    nm = name_of(n)
                    if nm: out.append(dict(short=nm, start=srow, start_dec=srow, end=v.end_point[0] + 1, name_row=srow))
            elif t == "pair":  # object-literal method: { overview: () => ... }
                k = n.child_by_field_name("key"); v = n.child_by_field_name("value")
                if k is not None and v is not None and v.type in ("arrow_function", "function_expression", "function"):
                    out.append(dict(short=txt(k), start=srow, start_dec=srow, end=v.end_point[0] + 1, name_row=srow))
        elif lang == "csharp" and t in ("class_declaration", "struct_declaration", "interface_declaration", "enum_declaration", "record_declaration",
                                         "record_struct_declaration", "method_declaration", "constructor_declaration", "destructor_declaration",
                                         "local_function_statement", "property_declaration", "operator_declaration", "indexer_declaration"):
            nm = name_of(n)
            if nm: out.append(dict(short=nm, start=srow, start_dec=srow, end=erow, name_row=n.child_by_field_name("name").start_point[0] + 1))
        for c in n.children:
            visit(c)
    visit(tree.root_node)
    return out

def truth_for(files):
    if lang == "clang":
        t = json.load(open(sys.argv[sys.argv.index("--clang-truth") + 1]))["defs"]
        out = collections.defaultdict(list)
        for usr, (f, s, e, qn) in t.items():
            out[f].append(dict(short=qn.rsplit(".", 1)[-1], start=s, start_dec=s, end=e, name_row=s))
        return out
    out = collections.defaultdict(list)
    for f in files:
        if f.endswith(EXT[lang]):
            try:
                out[f] = ts_defs(repo / f, lang)
            except Exception:
                pass
    return out

syms = load_symbols()
files = [f for f in syms if (f.endswith(EXT.get(lang, ("",))) if lang != "clang" else True)]
truth = truth_for(files if lang != "clang" else syms)
callable_kinds = ("function", "method", "class", "enum", "struct", "interface")
m = collections.Counter(); starts = collections.Counter(); ends = collections.Counter(); edist = []
matched_truth = set(); ambiguous_names = collections.Counter(); all_short = collections.Counter()
for f, ss in syms.items():
    if f not in truth and lang != "clang":
        continue
    if lang == "clang" and f not in truth:
        continue
    for s in ss:
        if s["kind"] not in callable_kinds:
            continue
        m["graph_symbols"] += 1
        all_short[s["short"]] += 1
        if s["ls"] is None or s["le"] is None:
            m["missing_range"] += 1; continue
        cands = [(abs(t["name_row"] - s["ls"]), i, t) for i, t in enumerate(truth[f]) if t["short"] == s["short"]]
        if not cands:
            m["no_truth_match"] += 1; continue
        d, i, t = min(cands, key=lambda c: c[0])
        if d > WINDOW:
            m["no_truth_match"] += 1; continue
        m["matched"] += 1; matched_truth.add((f, i))
        ds = s["ls"] - t["name_row"]
        starts["== name row" if ds == 0 else "== node start" if s["ls"] == t["start"] else "== decorator start" if s["ls"] == t["start_dec"] else "within 1 line" if abs(ds) <= 1 else "off by more"] += 1
        de = s["le"] - t["end"]
        edist.append(de)
        ends["exact" if de == 0 else "short by 1-2 lines" if -2 <= de < 0 else "long by 1-2 lines" if 0 < de <= 2 else "cuts short (>2 lines)" if de < -2 else "over-reads (>2 lines)"] += 1
n_truth = sum(len(v) for f, v in truth.items() if f in syms)
res = dict(repo=repo.name, lang=lang, graph_symbols=m["graph_symbols"], truth_defs=n_truth, matched=m["matched"],
           graph_missing_range=m["missing_range"], graph_without_truth=m["no_truth_match"],
           truth_recall=round(len(matched_truth) / max(1, n_truth), 3),
           graph_precision=round(m["matched"] / max(1, m["graph_symbols"] - m["missing_range"]), 3),
           start=dict(starts), end=dict(ends),
           end_exact_pct=round(100 * ends["exact"] / max(1, sum(ends.values())), 1),
           end_within_2_pct=round(100 * (ends["exact"] + ends["short by 1-2 lines"] + ends["long by 1-2 lines"]) / max(1, sum(ends.values())), 1),
           median_end_error=sorted(edist)[len(edist) // 2] if edist else None,
           short_names_with_more_than_one_symbol_pct=round(100 * sum(1 for k, v in all_short.items() if v > 1) / max(1, len(all_short)), 1))
print(json.dumps(res))
