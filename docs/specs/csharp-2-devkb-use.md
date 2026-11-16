# devkb used on its own code for C# round 2 (SPEC-DEVKB-CSHARP-2)

Packs taken from devkb's graph of its own repository (commit `3c9fa15d04`, the 0.2.4 merge) before any change.

What they decided:

- **File pack for `devkb/csharp_symbols.py`**: only `add_to_graph` (from `build_symbols.py`), `extract`, `mask` (tests)
  and `tests_in_text` (from `test_discovery.py`) are called from outside. So the performance work and the resolver
  changes could stay inside the module, with one rule to prove nothing else moved: the graph must stay byte-identical
  after the performance changes (checked on five repositories, and `mask` on all 9,309 files).
- **Refactor pack for `extract`**: two callers, both listed with their line; coverage complete. Adding an optional
  `stats` argument (for `bench/cs_stats.py`) cannot break them.
- **Refactor pack for `_Index.member`**: one caller file, and a recursive call. The pack also showed a devkb defect on
  the way: the recursive call's evidence line is the definition line (`csharp_symbols.py:495`) instead of the call
  (`:504`). Recorded as a follow-up for the Python extractor.
- **`refactor _calls_in`**: "cannot resolve unambiguously; search the code". Correct: a private helper with one
  caller in the same file; the pack declined rather than guessed.


---

## Graph pack: before editing `devkb/csharp_symbols.py`

Built from the dev-process graph at commit `3c9fa15d04`. None of the files below has changed since; the line numbers are current.

## Functions other files call (4 of 35)
- `add_to_graph` — 1 file(s): `devkb/build_symbols.py:1258: csharp_symbols.add_to_graph(g, repo_root)`
- `extract` — 1 file(s): `tests/test_csharp_symbols.py:240: _, calls = csharp_symbols.extract(_repo(tmp_path))`
- `mask` — 1 file(s): `tests/test_csharp_symbols.py:201: masked = csharp_symbols.mask((root / "src/Shop.Core/Order.cs").read_text())`
- `tests_in_text` — 1 file(s): `devkb/test_discovery.py:78: return tests_in_text(text)`

## Files that depend on it (3)
- `devkb/build_symbols.py`
- `devkb/test_discovery.py`
- `tests/test_csharp_symbols.py`

## Tests that exercise it, directly or through callers (11)
- `devkb/test_discovery.py` — `devkb/test_discovery.py:78: return tests_in_text(text)`
- `tests/test_csharp_symbols.py` (+4 more tests) — `tests/test_csharp_symbols.py:221: g = build_symbols.extract(root)`
- `tests/test_devkb_audit_efficiency_odsf314.py` — `tests/test_devkb_audit_efficiency_odsf314.py:81: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_baseline_symbols_odsf042.py` (+3 more tests) — `tests/test_devkb_bl_baseline_symbols_odsf042.py:133: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_containment_errors_criticality_odsf043.py` (+12 more tests) — `tests/test_devkb_bl_containment_errors_criticality_odsf043.py:146: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_crossfile_ts_api_odsf043.py` (+5 more tests) — `tests/test_devkb_bl_crossfile_ts_api_odsf043.py:58: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_call_resolution_odsf305.py` (+7 more tests) — `tests/test_devkb_call_resolution_odsf305.py:42: assert ("app/run.py::go", "lib/store.py::save_record") in _calls(build_symbols.extract(root))`
- `tests/test_devkb_coverage_classes_odsf313.py` (+5 more tests) — `tests/test_devkb_coverage_classes_odsf313.py:43: g = build_symbols.extract(_repo(tmp_path))`
- `tests/test_devkb_pull_requests_adr007.py` — `tests/test_devkb_pull_requests_adr007.py:75: build_symbols.build(str(root))`
- `tests/test_devkb_typed_calls_odsf312.py` — `tests/test_devkb_typed_calls_odsf312.py:35: g = build_symbols.extract(tmp_path)`
- `tests/test_reexports_module_calls.py` (+3 more tests) — `tests/test_reexports_module_calls.py:42: g = build_symbols.extract(root)`

Run: `python3 -m pytest devkb/test_discovery.py tests/test_csharp_symbols.py tests/test_devkb_audit_efficiency_odsf314.py tests/test_devkb_bl_baseline_symbols_odsf042.py tests/test_devkb_bl_containment_errors_criticality_odsf043.py tests/test_devkb_bl_crossfile_ts_api_odsf043.py tests/test_devkb_call_resolution_odsf305.py tests/test_devkb_coverage_classes_odsf313.py tests/test_devkb_pull_requests_adr007.py tests/test_devkb_typed_calls_odsf312.py tests/test_reexports_module_calls.py -q`

## Coverage
**Incomplete: 47 call site(s) under this name could not be attributed.** 20 symbols share the name, so most may be calls to the others. They are in 30 files; the 10 with the most: `devkb/github.py`, `devkb/csharp_symbols.py`, `devkb/edge_truth.py`, `devkb/bench/module_truth.py`, `devkb/process_api.py`, `devkb/bench/oco_tasks.py`, `devkb/call_recall.py`, `bench/exercises/adr007/acceptance.py`, `devkb/bench/cli_tasks.py`, `devkb/bench/confirm_tasks.py`. Search the whole repository for the rest.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---


---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::_Index.member`

Built from the dev-process graph at commit `3c9fa15d04`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:495: def member(self, tq: tuple[str, ...], name: str, seen: frozenset = frozenset()) -> dict | None:`.

## Files with a direct caller (1, tests included)
- `devkb/csharp_symbols.py` — `devkb/csharp_symbols.py:495: def member(self, tq: tuple[str, ...], name: str, seen: frozenset = frozenset()) -> dict | None:`

## Test files among them (0)
- none

## Coverage
**Incomplete: 1 call site(s) under this name could not be attributed.** They are in files already listed above; check those files' other calls under this name.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: refactor

The graph cannot resolve `_calls_in` unambiguously. Search the code.

---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::extract`

Built from the dev-process graph at commit `3c9fa15d04`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:622: def extract(repo_root: Path) -> tuple[list[dict], list[dict]]:`.

## Files with a direct caller (2, tests included)
- `devkb/csharp_symbols.py` — `devkb/csharp_symbols.py:676: symbols, calls = extract(repo_root)`
- `tests/test_csharp_symbols.py` (+2 more) — `tests/test_csharp_symbols.py:240: _, calls = csharp_symbols.extract(_repo(tmp_path))`

## Test files among them (1)
- `tests/test_csharp_symbols.py`

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.
