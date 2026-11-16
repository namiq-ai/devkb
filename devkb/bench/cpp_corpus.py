"""The C/C++ corpus check (ADR-DEVKB-008 §7, DKB-006): `make cpp-check`. Not part of gate-1 or gate-2 (they stay offline).

  python3 -m devkb.bench.cpp_corpus [--repos cJSON,fmt] [--cache DIR] [--runs 2] [--skip-budget] [--sample 100]

For each pinned repository it fetches (shallow, outside this repository) and refuses any commit other than the pin,
builds the graph, and measures caller precision and recall against the independent regex truth (`cpp_truth`), the
Complete rule (a symbol whose pack says Complete must miss no determinate true caller: floor 1.0, not tunable), the
build-time budget, and the dependency list. Exit 0 only if every check holds.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devkb.bench import cpp_truth  # noqa: E402

CORPUS = Path(__file__).with_name("cpp_corpus.json")
ALLOWED_DEPENDENCIES = ["pyyaml>=6"]
LANGUAGES = ("c", "cpp")
BOUNDARY_SOURCES = ("extern-c", "ctypes", "cffi", "pyc-api", "pybind11")


class PinMismatch(RuntimeError):
    pass


def load(path: Path = CORPUS) -> dict:
    return json.loads(path.read_text())


def cache_dir(arg: str | None = None) -> Path:
    return Path(arg or os.environ.get("DEVKB_CPP_CORPUS") or Path.home() / ".cache" / "devkb" / "cpp-corpus")


def head(path: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True).stdout.strip()


def verify_pin(path: Path, commit: str) -> None:
    got = head(path)
    if got != commit:
        raise PinMismatch(f"{path.name}: HEAD is {got or 'unknown'}, the corpus pins {commit}; refusing to measure")


def fetch(repo: dict, cache: Path) -> Path:
    """The pinned checkout under `cache`: a shallow clone of exactly the pinned commit, or the existing one if it is."""
    dest = cache / repo["name"]
    if not dest.exists():
        dest.mkdir(parents=True)
        for cmd in (["init", "-q"], ["remote", "add", "origin", repo["url"]], ["fetch", "-q", "--depth", "1", "origin", repo["commit"]],
                    ["checkout", "-q", "FETCH_HEAD"]):
            subprocess.run(["git", *cmd], cwd=dest, check=True)
    verify_pin(dest, repo["commit"])
    return dest


# ── dependencies ──────────────────────────────────────────────────────────────────
def check_dependencies(root: Path = ROOT, exemptions: dict | None = None) -> list[str]:
    """Problems with the dependency list; empty when `dependencies` is `["pyyaml>=6"]` and `devkb` imports only the
    standard library, `yaml`, itself and its own sibling modules. `exemptions` (from `cpp_corpus.json`, each with a
    stated reason) names the optional, lazily imported modules the tree already had before DKB-001."""
    problems = []
    text = (root / "pyproject.toml").read_text()
    m = re.search(r"(?m)^dependencies\s*=\s*(\[[^\]]*\])", text)
    deps = ast.literal_eval(m.group(1)) if m else None
    if deps != ALLOWED_DEPENDENCIES:
        problems.append(f"pyproject.toml dependencies is {deps}, expected {ALLOWED_DEPENDENCIES}")
    exemptions = load()["dependency_exemptions"] if exemptions is None else exemptions
    siblings = {p.stem for p in (root / "devkb").rglob("*.py")}
    allowed = set(sys.stdlib_module_names) | {"yaml", "devkb"} | siblings | set(exemptions)
    for path in sorted((root / "devkb").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else []
            for mod in mods:
                if mod.split(".")[0] not in allowed:
                    problems.append(f"{path.relative_to(root)} imports {mod}")
    return problems


# ── measurement ───────────────────────────────────────────────────────────────────
def _short(key: str) -> str:
    return key.split("::", 1)[1].rsplit(".", 1)[-1]


def measure(path: Path, sample: int = 100, seed: int = 20261116, graph=None, truth=None) -> dict:
    """Precision, recall, indeterminate counts, the Complete rule and forbidden edges for one checkout."""
    from devkb import build_symbols
    g = graph or build_symbols.extract(path)
    truth = truth or cpp_truth.build(path)
    syms = {n.natural_key: n.props for n in g.nodes("Symbol") if n.source == "cpp-symbols"}
    by_file: dict[str, list[tuple[int, int, str]]] = {}
    for key, p in syms.items():
        by_file.setdefault(key.split("::", 1)[0], []).append((p["line_start"], p["line_end"], key))
    for lst in by_file.values():
        lst.sort()

    def enclosing(file: str, line: int) -> str | None:
        best = None
        for a, b, key in by_file.get(file, ()):
            if a > line:
                break
            if a <= line <= b and syms[key]["kind"] in ("function", "method", "test"):
                best = key
        return best

    esource = {(e.src, e.dst): e.source for e in g.edges("CALLS") if (e.source.startswith("cpp-") or e.source in BOUNDARY_SOURCES)
               and e.src in syms and e.dst in syms}
    edges = set(esource)
    correct = wrong = indeterminate = no_site = 0
    forbidden = []
    by_lang = {lang: {"edges": 0, "correct": 0, "wrong": 0, "indeterminate": 0, "unmapped": 0} for lang in LANGUAGES}
    by_source: dict[str, dict] = {}
    for src, dst in sorted(edges):
        name, sfile, dfile = _short(dst), src.split("::", 1)[0], dst.split("::", 1)[0]
        if name in cpp_truth.LIBC and sfile != dfile:
            forbidden.append((src, dst))
        p = syms[src]
        sites = [s for s in truth.sites.get(name, []) if s.file == sfile and p["line_start"] <= s.line <= p["line_end"]]
        buckets = [by_lang.setdefault(p.get("language") or "cpp", {"edges": 0, "correct": 0, "wrong": 0, "indeterminate": 0, "unmapped": 0}),
                   by_source.setdefault(esource[(src, dst)], {"edges": 0, "correct": 0, "wrong": 0, "indeterminate": 0, "unmapped": 0})]
        for b in buckets:
            b["edges"] += 1
        if not sites:
            no_site += 1
            outcome = "unmapped"
        elif any(s.target and s.target.file == dfile for s in sites):
            correct += 1
            outcome = "correct"
        elif all(s.target for s in sites):
            wrong += 1
            outcome = "wrong"
        else:
            indeterminate += 1
            outcome = "indeterminate"
        for b in buckets:
            b[outcome] += 1
    determinate_edges = correct + wrong
    precision = correct / determinate_edges if determinate_edges else 1.0
    for b in list(by_lang.values()) + list(by_source.values()):
        det = b["correct"] + b["wrong"]
        b["precision"] = round(b["correct"] / det, 4) if det else 1.0

    # targets: functions the truth knows; at least half with a name defined more than once, when that many exist
    def sample_block(language: str | None) -> dict:
        rng = random.Random(seed)
        cands = sorted(k for k, p in syms.items() if p["kind"] in ("function", "method") and _short(k) in truth.defs
                       and (language is None or p.get("language") == language))
        multi = [k for k in cands if len(truth.defs[_short(k)]) > 1]
        single = [k for k in cands if len(truth.defs[_short(k)]) == 1]
        rng.shuffle(multi)
        rng.shuffle(single)
        want_multi = min(len(multi), (sample + 1) // 2)
        targets = multi[:want_multi] + single[:sample - want_multi]
        targets = (targets + multi[want_multi:])[:sample]
        complete = _complete_flags(g, path, targets)
        sites_total = sites_hit = misses = complete_checked = 0
        miss_detail = []
        for t in targets:
            tname, tfile = _short(t), t.split("::", 1)[0]
            true_sites = [s for s in truth.sites.get(tname, []) if s.target and s.target.file == tfile]
            found, missing = 0, []
            for s in true_sites:
                caller = enclosing(s.file, s.line)
                if caller is None:
                    continue
                if (caller, t) in edges:
                    found += 1
                else:
                    missing.append(f"{s.file}:{s.line}")
            sites_total += found + len(missing)
            sites_hit += found
            if complete.get(t):
                complete_checked += 1
                if missing:
                    misses += 1
                    miss_detail.append({"target": t, "missing": missing[:5]})
        return {"recall": round(sites_hit / sites_total if sites_total else 1.0, 4), "true_sites": sites_total, "targets": len(targets),
                "targets_multi_defined": want_multi, "complete_packs": complete_checked, "complete_misses": misses,
                "complete_miss_detail": miss_detail[:5]}

    # story 2.7: how many C packs carry the exported-symbol note (every non-static C function does), so the owner can judge the noise
    c_funcs = [p for p in syms.values() if p.get("language") == "c" and p["kind"] == "function"]
    exported_note = {"c_functions": len(c_funcs), "with_note": sum(1 for p in c_funcs if p.get("abi_exported")),
                     "share": round(sum(1 for p in c_funcs if p.get("abi_exported")) / len(c_funcs), 4) if c_funcs else 0.0}
    whole = sample_block(None)
    recall, sites_total, targets_n, want_multi = whole["recall"], whole["true_sites"], whole["targets"], whole["targets_multi_defined"]
    complete_checked, misses, miss_detail = whole["complete_packs"], whole["complete_misses"], whole["complete_miss_detail"]
    per_language = {}
    for lang in LANGUAGES:
        if any(p.get("language") == lang for p in syms.values()):
            per_language[lang] = {**by_lang[lang], **sample_block(lang)}
    return {"files": truth.files, "symbols": len(syms), "edges": len(edges), "precision": round(precision, 4),
            "determinate_edges": determinate_edges, "wrong_edges": wrong, "indeterminate_edges": indeterminate, "edges_without_site": no_site,
            "recall": round(recall, 4), "true_sites": sites_total, "targets": targets_n, "targets_multi_defined": want_multi,
            "complete_packs": complete_checked, "complete_misses": misses, "complete_miss_detail": miss_detail[:5],
            "by_language": per_language, "by_source": by_source, "exported_note": exported_note,
            "forbidden_edges": forbidden[:10], "forbidden_count": len(forbidden)}


def header_agreement(file_languages: dict[str, str], header_langs: dict[str, list[str]]) -> dict:
    """Reported beside the counts, never folded into them (story 1.6): the share of headers whose devkb language equals the
    language of the translation units that include them, by the compiler's inclusion graph (`truth_clang.py` `header_langs`)."""
    agree, disagree = 0, []
    for header, langs in sorted(header_langs.items()):
        mine = file_languages.get(header)
        if mine is None:
            continue
        expected = "cpp" if set(langs) == {"cpp"} else "c"          # a header any C unit includes must be readable as C
        if mine == expected:
            agree += 1
        else:
            disagree.append(f"{header}: devkb {mine}, included by {'+'.join(langs)} units")
    total = agree + len(disagree)
    return {"headers": total, "agree": agree, "share": round(agree / total, 4) if total else 1.0, "disagree": disagree}


def _complete_flags(g, path: Path, keys: list[str]) -> dict[str, bool]:
    """Whether the real pack coverage says Complete for each key (the API reads a store written from the graph)."""
    from devkb import process_api
    from devkb.project_context import ProjectContext
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        d = g.to_dict()
        (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
        (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
        (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-16T00:00:00+00:00", "git_head": head(path)}))
        ctx = ProjectContext(code="CPP", repo_root=path, ticket_prefix="CPP", issues_dir=path / "issues", tests_dir=path / "tests",
                             sprint_dir=path / "h", devkb_dir=store, board_file=path / "b.md", wp_map_file=path / "w.json")
        original = process_api.resolve
        process_api.resolve = lambda code: ctx
        try:
            api = process_api.ProcessAPI("CPP", telemetry=False)
            out = {}
            for k in keys:
                i, _err = api._resolve(k)
                out[k] = bool(i is not None and api._coverage([i]).get("complete"))
            return out
        finally:
            process_api.resolve = original


def build_seconds(path: Path, runs: int) -> float:
    from devkb import build_symbols
    best = float("inf")
    for _ in range(max(1, runs)):
        t = time.time()
        build_symbols.extract(path)
        best = min(best, time.time() - t)
    return best


# ── the check ─────────────────────────────────────────────────────────────────────
def verdict(name: str, m: dict, floors: dict) -> list[str]:
    """Why a measurement fails its floors (empty: passes)."""
    why = []
    if m["precision"] < floors.get("precision", 0.95):
        why.append(f"{name}: precision {m['precision']} below the floor {floors.get('precision', 0.95)}")
    if floors.get("recall") is not None and m["recall"] < floors["recall"]:
        why.append(f"{name}: recall {m['recall']} below the floor {floors['recall']}")
    if m["complete_misses"]:
        why.append(f"{name}: {m['complete_misses']} pack(s) say Complete yet miss a true caller {m['complete_miss_detail']}")
    for lang, fl in (floors.get("by_language") or {}).items():
        got = m.get("by_language", {}).get(lang)
        if got is None:
            continue
        if got["precision"] < fl.get("precision", 0.95):
            why.append(f"{name}/{lang}: precision {got['precision']} below the floor {fl.get('precision', 0.95)}")
        if fl.get("recall") is not None and got["recall"] < fl["recall"]:
            why.append(f"{name}/{lang}: recall {got['recall']} below the floor {fl['recall']}")
    for lang, got in m.get("by_language", {}).items():
        if got["complete_misses"] and lang != "cpp":
            why.append(f"{name}/{lang}: {got['complete_misses']} pack(s) say Complete yet miss a true caller {got['complete_miss_detail']}")
    for src, fl in (floors.get("by_source") or {}).items():
        got = m.get("by_source", {}).get(src)
        if got is not None and got["precision"] < fl.get("precision", 0.95):
            why.append(f"{name}/{src}: precision {got['precision']} below the floor {fl.get('precision', 0.95)}")
    if m["forbidden_count"]:
        why.append(f"{name}: a C library name is linked across files {m['forbidden_edges'][:3]}")
    return why


def check_path(path: Path, name: str, floors: dict, sample: int = 100) -> tuple[dict, list[str]]:
    m = measure(path, sample)
    return m, verdict(name, m, floors)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repos", default="", help="comma-separated names; default: all of the corpus")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--runs", type=int, default=2, help="build runs for the budget; the best counts")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--skip-budget", action="store_true")
    ap.add_argument("--json", default=None, help="write the measurements here")
    ap.add_argument("--truth-dir", default=None, help="a directory of `truth_<repo>.json` from bench/cpp/truth_clang.py: "
                    "adds the header-language agreement with the compiler's inclusion graph")
    args = ap.parse_args(argv)
    corpus = load()
    wanted = {r for r in args.repos.split(",") if r}
    failures: list[str] = check_dependencies()
    print("dependencies: " + ("ok (pyyaml>=6 only)" if not failures else "; ".join(failures)))
    report: dict = {"reference_machine": corpus.get("reference_machine"), "repos": {}}
    for repo in corpus["repos"]:
        if wanted and repo["name"] not in wanted:
            continue
        try:
            path = fetch(repo, cache_dir(args.cache))
        except PinMismatch as exc:
            failures.append(str(exc))
            print(f"{repo['name']}: REFUSED {exc}")
            continue
        m, why = check_path(path, repo["name"], corpus["floors"].get(repo["name"], {}), args.sample)
        if not args.skip_budget:
            budget = corpus["budgets"].get(repo["name"], corpus["budgets"]["default_seconds"])
            secs = build_seconds(path, args.runs)
            m["build_seconds"], m["budget_seconds"] = round(secs, 1), budget
            if secs > budget:
                why.append(f"{repo['name']}: build took {secs:.1f}s, budget {budget}s")
        report["repos"][repo["name"]] = m
        failures += why
        tfile = Path(args.truth_dir) / f"truth_{repo['name']}.json" if args.truth_dir else None
        if tfile is not None and tfile.exists():
            from devkb import build_symbols
            hl = json.loads(tfile.read_text()).get("header_langs", {})
            langs = {n.natural_key: n.props.get("language") for n in build_symbols.extract(path).nodes("File") if n.props.get("language")}
            ha = header_agreement(langs, hl)
            m["header_agreement"] = {k: ha[k] for k in ("headers", "agree", "share")}
            print(f"  {repo['name']}: header language agrees with the compiler's includers for {ha['agree']} of {ha['headers']} headers ({ha['share']:.1%})")
            for line in ha["disagree"][:20]:
                print("    disagree: " + line)
        else:
            print(f"  {repo['name']}: header-language agreement not measured (no compiler truth: pass --truth-dir)")
        for lang, b in m["by_language"].items():
            print(f"  {repo['name']}/{lang}: precision {b['precision']} recall {b['recall']} ({b['correct']} correct, {b['wrong']} wrong, "
                  f"{b['indeterminate']} indeterminate, {b['unmapped']} unmapped ends) complete packs {b['complete_packs']} misses {b['complete_misses']}")
        n = m["exported_note"]
        print(f"  {repo['name']}: {n['with_note']} of {n['c_functions']} C functions ({n['share']:.1%}) carry the exported-symbol note")
        for src, b in m["by_source"].items():
            if src in BOUNDARY_SOURCES:
                print(f"  {repo['name']}/{src}: {b['edges']} edges, precision {b['precision']}, {b['unmapped']} unmapped ends")
        print(f"{repo['name']}: precision {m['precision']} ({m['determinate_edges']} determinate edges, {m['indeterminate_edges']} indeterminate, "
              f"{m['edges_without_site']} without a site) recall {m['recall']} ({m['true_sites']} sites) complete packs {m['complete_packs']} "
              f"misses {m['complete_misses']}" + (f" build {m['build_seconds']}s/{m['budget_seconds']}s" if "build_seconds" in m else ""))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
    for f in failures:
        print("FAIL " + f, file=sys.stderr)
    print("reference_machine:", json.dumps(corpus.get("reference_machine")))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
