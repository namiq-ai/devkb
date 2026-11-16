"""Chain questions for C# and their truth, without a compiler (SPEC-DEVKB-CSHARP-3, value benchmark).

  python bench/cs_chain_truth.py REPO [--pick N] [--seed 2032]   ->  JSON: [{target, file, truth, tests, depth}]

The question an agent is asked: "list every production method that can reach F, at any depth, and the test files that
exercise it". C++ used libclang for truth. No .NET SDK is assumed here, so the truth is the *text-visible* call graph:
starting from F, every production method whose body contains `Name(` for a method already in the set, repeated to a
fixed point. Method bodies come from the scanner (`csharp_symbols.scan_file`), not from its call resolution.

That is exact only when names are: a target is accepted only if every method name in its closure is declared by one
type only (its overloads and partial files count as one method) and is not a common .NET member name, so a textual
`Name(` can mean nothing else. What it cannot see:
calls through delegates or method groups (`Run(Handler)`), reflection, and calls through an interface or base method
of a different name. Test files: the test files whose code calls any method of the closure or F itself.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkb import csharp_dotnet, csharp_symbols, process_api  # noqa: E402

COMMON = set().union(*csharp_dotnet.MEMBERS.values()) | csharp_dotnet.DOTNET_EXTENSIONS | csharp_dotnet.LINQ_LAMBDA


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--pick", type=int, default=2)
    ap.add_argument("--seed", type=int, default=2032)
    ap.add_argument("--min", type=int, default=6)
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    repo = Path(a.repo)
    scans, methods = {}, []
    for rel in csharp_symbols.list_files(repo):
        p = repo / rel
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        sc = csharp_symbols.scan_file(rel, p.read_text(errors="replace"))
        scans[rel] = sc
        for s in sc["symbols"]:
            s["rel"] = rel
            if s["kind"] in ("method", "function") and s.get("body"):
                methods.append(s)
    owners: dict[str, set] = {}                          # method name -> the types declaring it
    type_names: set[str] = set()
    for sc in scans.values():
        for s in sc["symbols"]:
            if s["kind"] in ("method", "function"):
                owners.setdefault(s["name"], set()).add(s["qparts"][:-1])
            elif s["kind"] in ("class", "enum"):
                type_names.add(s["name"])
    # every method body's call names, once
    calls_in: list[tuple[dict, set[str]]] = []
    name_re = re.compile(r"(?<![\w@])@?([A-Za-z_]\w*)\s*(?:<[^<>();{}]*(?:<[^<>();{}]*>[^<>();{}]*)*>)?\s*\(")
    for s in methods:
        text = "".join(scans[s["rel"]]["masked"][b0:b1] for b0, b1 in s["body"])
        calls_in.append((s, set(name_re.findall(text))))

    def unique(name: str) -> bool:
        # one method family: every definition in one type (overloads, partial files); not also a type's name
        return len(owners.get(name, ())) == 1 and name not in type_names and name not in COMMON \
            and name != "ctor" and len(name) >= 4

    callers_of: dict[str, list[dict]] = {}
    for m, names in calls_in:
        for n in names:
            callers_of.setdefault(n, []).append(m)

    def closure(target: str):
        """(exact, uncertain, depth). A method whose body calls `name` is in the closure; it is *exact* when a textual
        call to `name` can only mean a closure method (every name on its path is one method family), *uncertain*
        when its path crosses an ambiguous name (scored as neither right nor wrong)."""
        state: dict[int, tuple[dict, bool, int]] = {}            # id(method) -> (method, exact, depth)
        best: dict[str, bool] = {target: True}                   # name -> already expanded exactly?
        queue = [(target, True, 0)]
        while queue:
            name, exact_name, d = queue.pop(0)
            for m in callers_of.get(name, ()):
                if m["name"] == target:
                    continue
                prev = state.get(id(m))
                if prev and (prev[1] or not exact_name):
                    continue
                state[id(m)] = (m, exact_name, d + 1)
                nm, ok = m["name"], exact_name and unique(m["name"])
                if nm not in best or (ok and not best[nm]):
                    best[nm] = ok
                    queue.append((nm, ok, d + 1))
        exact = [v for v in state.values() if v[1]]
        uncertain = [v for v in state.values() if not v[1]]
        return exact, uncertain, max((v[2] for v in exact), default=0)

    prod = [s for s in methods if not process_api.is_test_path(s["rel"]) and unique(s["name"])]
    random.seed(a.seed)
    random.shuffle(prod)
    picked = []
    label = lambda m: ".".join(m["qparts"][-2:])                 # noqa: E731
    for s in prod:
        exact, uncertain, depth = closure(s["name"])
        callers = [m for m, _, _ in exact if not process_api.is_test_path(m["rel"])]
        unsure = [m for m, _, _ in uncertain if not process_api.is_test_path(m["rel"])]
        truth = sorted({label(m) for m in callers})
        maybe = sorted({label(m) for m in unsure} - set(truth))
        if not (a.min <= len(truth) <= a.max) or depth < 2 or len(maybe) > len(truth):
            continue
        names = {m["name"] for m in callers} | {s["name"]}
        tests = sorted({m["rel"] for m, _, _ in exact if process_api.is_test_path(m["rel"])} |
                       {m["rel"] for m, ns in calls_in if process_api.is_test_path(m["rel"]) and ns & names})
        picked.append({"target": label(s), "name": s["name"], "file": s["rel"], "line": s["line_start"],
                       "depth": depth, "truth": truth, "uncertain": maybe, "tests": tests})
        if len(picked) >= a.pick:
            break
    print(json.dumps(picked, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
