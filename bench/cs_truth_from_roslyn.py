"""Rewrite chain questions' truth from the compiler's call graph (bench/roslyn_truth, run on GitHub's runners).

  python bench/cs_truth_from_roslyn.py QUESTIONS.json TRUTH_DIR OUT.json

TRUTH_DIR holds `truth-<repo>.json` per repository (the workflow's artifacts). For each question the target is every
definition whose file is the question's file and whose qualified name ends `.Name` (an overload family). Truth: the
production methods that reach it through statically bound calls, at any depth. *Uncertain* (neither right nor wrong
when scored): methods that reach it only through virtual or interface dispatch (they call the base or interface method
that the target implements or overrides), or only through a method group registered as a callback (the truth's
`delegates`: they reach it when the callback is invoked), which do reach it at run time. Property and indexer reads are
edges to the accessor (truth files from before they were, without `accessor_edges`, stop at a property). Tests: the test files holding a method that
reaches it. The text-visible truth the question had before is kept as `text_truth` for comparison.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkb import process_api  # noqa: E402

NON_PRODUCTION = __import__("re").compile(r"(^|/)(bench|benchmarks?|[^/]*\.Benchmarks?|samples?|[^/]*\.Samples?|Snippets|"
                                         r"docs?|examples?|[^/]*\.Examples?)(/|$)", __import__("re").I)


def is_production(rel: str) -> bool:
    """Shipped code: not a test, benchmark, sample, documentation snippet or example."""
    return not process_api.is_test_path(rel) and not NON_PRODUCTION.search(rel)


REPO_ID = {"MediatR": "mediatr", "FluentValidation": "fluentvalidation", "Polly": "polly", "jellyfin": "jellyfin",
           "efcore": "efcore"}


def closure(starts: set[str], callers: dict, bases_of: dict, impls_of: dict, use_dispatch: bool,
            holders: dict | None = None) -> set[str]:
    seen, todo = set(starts), list(starts)
    while todo:
        x = todo.pop()
        nxt = set(callers.get(x, ()))
        if use_dispatch:
            nxt |= (holders or {}).get(x, set())   # who registers it as a callback reaches it when the callback runs
            for b in bases_of.get(x, ()):          # who calls the base/interface method reaches this implementation
                nxt |= callers.get(b, set())
                if b not in seen:
                    seen.add(b)
                    todo.append(b)
        for y in nxt - seen:
            seen.add(y)
            todo.append(y)
    return seen - starts


def main() -> int:
    qs = json.loads(Path(sys.argv[1]).read_text())
    tdir, out = Path(sys.argv[2]), Path(sys.argv[3])
    graphs = {}
    for q in qs:
        rid = REPO_ID[Path(q["repo"]).name]
        if rid not in graphs:
            graphs[rid] = json.loads((tdir / f"truth-{rid}.json").read_text())
        g = graphs[rid]
        defs = g["defs"]
        callers, bases_of, impls_of, holders = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
        for a, b in g.get("delegates", []):
            holders[b].add(a)
        for a, b in g["edges"]:
            callers[b].add(a)
        for impl, base in g["dispatch"]:
            bases_of[impl].add(base)
            impls_of[base].add(impl)
        starts = {i for i, (f, _s, _e, qn) in defs.items() if f == q["file"] and qn.split(".")[-1] == q["name"]}
        if not starts:
            print("no target found for", q["target"], file=sys.stderr)
            continue
        static = closure(starts, callers, bases_of, impls_of, False)
        dyn = closure(starts, callers, bases_of, impls_of, True, holders) - static
        label = lambda i: defs[i][3] if i in defs else i                       # noqa: E731
        prod = lambda ids: {i for i in ids if i in defs and is_production(defs[i][0])}  # noqa: E731
        other = lambda ids: {i for i in ids if i in defs and not is_production(defs[i][0])  # noqa: E731
                             and not process_api.is_test_path(defs[i][0])}
        truth = sorted({label(i) for i in prod(static)})
        if "text_truth" not in q:
            q["text_truth"], q["text_uncertain"], q["text_tests"] = q["truth"], q.get("uncertain", []), q.get("tests", [])
        q["truth"] = truth
        # neither right nor wrong: reached only through dispatch, or a caller in benchmark/sample/snippet code
        q["uncertain"] = sorted({label(i) for i in prod(dyn) | other(static | dyn)} - set(truth))
        q["tests"] = sorted({defs[i][0] for i in static if i in defs and process_api.is_test_path(defs[i][0])})
        # for scoring: which backticked names are production methods (others, such as type names in prose or test
        # methods, are neither right nor wrong)
        q["production_methods"] = sorted({qn.split(".")[-1] for f, _s, _e, qn in defs.values()
                                          if is_production(f) and not qn.endswith(".ctor")})
        q["truth_source"] = "roslyn"
        print(f"{q['target']}: compiler {len(truth)} (+{len(q['uncertain'])} via dispatch, {len(q['tests'])} test "
              f"files, static calls only) | text {len(q['text_truth'])}; in both {len(set(truth) & set(q['text_truth']))}")
    out.write_text(json.dumps(qs, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
