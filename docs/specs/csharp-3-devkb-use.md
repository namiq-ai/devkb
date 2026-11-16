# devkb used on its own code for C# round 3 (SPEC-DEVKB-CSHARP-3)

Packs from devkb's graph of its own repository at `af6c6ba` (the 0.2.5 merge), taken before any change.

What they decided:

- **File pack for `devkb/csharp_symbols.py`**: seven names are used outside the module, all but two only by its own
  tests (`_arg_count`, `_arity`, `_locals`, `mask`, `extract`); `add_to_graph` (build) and `tests_in_text` (test
  discovery) are the only production entry points. So the expression typing could replace `_calls_in` wholesale
  while keeping every public signature: `_locals` kept its simple-name contract (a test pins it) and gained a
  `_locals_full` beside it; `_arg_count` stayed for its tests while `_args` does the new work.
- **Refactor pack for `_locals`**: one production caller (`_calls_in`) and one test line; coverage complete.
- **Refactor pack for `_ret_type`**: one caller (`_member_head`); coverage complete. Return types with generics were
  added as `ret_full` beside it rather than by changing it.
- **Refactor packs for `_Index.extension` and `_Index.field_type`**: both "incomplete". Correct, and a finding about
  devkb's Python side: the calls go through `index: "_Index"`, a string annotation, which the Python extractor does
  not resolve; and the recursive call in `field_type` shows the definition line as its evidence (as in round 2).
  Both are recorded for the Python extractor; the C# work searched `csharp_symbols.py` for these two by hand.


---

## Graph pack: before editing `devkb/csharp_symbols.py`

Built from the dev-process graph at commit `af6c6ba12a`. None of the files below has changed since; the line numbers are current.

## Functions other files call (7 of 44)
- `_arg_count` — 1 file(s): `tests/test_csharp_symbols.py:334: assert csharp_symbols._arg_count(csharp_symbols.mask(text), text, 1) == n, text`
- `_arity` — 1 file(s): `tests/test_csharp_symbols.py:335: assert csharp_symbols._arity("int a, int b = 2, params object[] rest", False) == (1, None)`
- `_locals` — 1 file(s): `tests/test_csharp_symbols.py:378: assert csharp_symbols._locals("using var w = new Painter();") == {"w": "Painter"}`
- `add_to_graph` — 1 file(s): `devkb/build_symbols.py:1258: csharp_symbols.add_to_graph(g, repo_root)`
- `extract` — 1 file(s): `tests/test_csharp_symbols.py:297: syms, calls = csharp_symbols.extract(_repo(tmp_path))`
- `mask` — 1 file(s): `tests/test_csharp_symbols.py:334: assert csharp_symbols._arg_count(csharp_symbols.mask(text), text, 1) == n, text`
- `tests_in_text` — 1 file(s): `devkb/test_discovery.py:78: return tests_in_text(text)`

## Files that depend on it (3)
- `devkb/build_symbols.py`
- `devkb/test_discovery.py`
- `tests/test_csharp_symbols.py`

## Tests that exercise it, directly or through callers (11)
- `devkb/test_discovery.py` — `devkb/test_discovery.py:78: return tests_in_text(text)`
- `tests/test_csharp_symbols.py` (+12 more tests) — `tests/test_csharp_symbols.py:201: masked = csharp_symbols.mask((root / "src/Shop.Core/Order.cs").read_text())`
- `tests/test_devkb_audit_efficiency_odsf314.py` — `tests/test_devkb_audit_efficiency_odsf314.py:81: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_baseline_symbols_odsf042.py` (+3 more tests) — `tests/test_devkb_bl_baseline_symbols_odsf042.py:133: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_containment_errors_criticality_odsf043.py` (+12 more tests) — `tests/test_devkb_bl_containment_errors_criticality_odsf043.py:146: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_crossfile_ts_api_odsf043.py` (+5 more tests) — `tests/test_devkb_bl_crossfile_ts_api_odsf043.py:58: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_call_resolution_odsf305.py` (+7 more tests) — `tests/test_devkb_call_resolution_odsf305.py:42: assert ("app/run.py::go", "lib/store.py::save_record") in _calls(build_symbols.extract(root))`
- `tests/test_devkb_coverage_classes_odsf313.py` (+5 more tests) — `tests/test_devkb_coverage_classes_odsf313.py:43: g = build_symbols.extract(_repo(tmp_path))`
- `tests/test_devkb_pull_requests_adr007.py` — `tests/test_devkb_pull_requests_adr007.py:75: build_symbols.build(str(root))`
- `tests/test_devkb_typed_calls_odsf312.py` — `tests/test_devkb_typed_calls_odsf312.py:35: g = build_symbols.extract(tmp_path)`
- `tests/test_reexports_module_calls.py` (+3 more tests) — `tests/test_reexports_module_calls.py:124: g = build_symbols.extract(tmp_path)`

Run: `python3 -m pytest devkb/test_discovery.py tests/test_csharp_symbols.py tests/test_devkb_audit_efficiency_odsf314.py tests/test_devkb_bl_baseline_symbols_odsf042.py tests/test_devkb_bl_containment_errors_criticality_odsf043.py tests/test_devkb_bl_crossfile_ts_api_odsf043.py tests/test_devkb_call_resolution_odsf305.py tests/test_devkb_coverage_classes_odsf313.py tests/test_devkb_pull_requests_adr007.py tests/test_devkb_typed_calls_odsf312.py tests/test_reexports_module_calls.py -q`

## Coverage
**Incomplete: 50 call site(s) under this name could not be attributed.** 20 symbols share the name, so most may be calls to the others. They are in 32 files; the 10 with the most: `devkb/github.py`, `devkb/csharp_symbols.py`, `bench/cs_diff_sample.py`, `devkb/edge_truth.py`, `devkb/bench/module_truth.py`, `devkb/process_api.py`, `devkb/bench/oco_tasks.py`, `devkb/call_recall.py`, `bench/exercises/adr007/acceptance.py`, `devkb/bench/cli_tasks.py`. Search the whole repository for the rest.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::_Index.extension`

Built from the dev-process graph at commit `af6c6ba12a`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:640: def extension(self, name: str, n: int | None, rtype: str | None, near: tuple[str, ...]) -> dict | None:`.

## Files with a direct caller (0, tests included)

## Test files among them (0)
- none

(The defining file `devkb/csharp_symbols.py` is not counted as a caller.)

## Coverage
**Incomplete: 1 call site(s) under this name could not be attributed.** Search only these files for them: `devkb/csharp_symbols.py`.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::_Index.field_type`

Built from the dev-process graph at commit `af6c6ba12a`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:673: def field_type(self, tq: tuple[str, ...], name: str) -> str | None:`.

## Files with a direct caller (1, tests included)
- `devkb/csharp_symbols.py` — `devkb/csharp_symbols.py:673: def field_type(self, tq: tuple[str, ...], name: str) -> str | None:`

## Test files among them (0)
- none

## Coverage
**Incomplete: 1 call site(s) under this name could not be attributed.** They are in files already listed above; check those files' other calls under this name.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::_locals`

Built from the dev-process graph at commit `af6c6ba12a`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:701: def _locals(body: str) -> dict[str, str]:`.

## Files with a direct caller (2, tests included)
- `devkb/csharp_symbols.py` — `devkb/csharp_symbols.py:743: types.update(_locals(body))`
- `tests/test_csharp_symbols.py` — `tests/test_csharp_symbols.py:378: assert csharp_symbols._locals("using var w = new Painter();") == {"w": "Painter"}`

## Test files among them (1)
- `tests/test_csharp_symbols.py`

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/csharp_symbols.py::_ret_type`

Built from the dev-process graph at commit `af6c6ba12a`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/csharp_symbols.py:352: def _ret_type(rest: str) -> str | None:`.

## Files with a direct caller (1, tests included)
- `devkb/csharp_symbols.py` — `devkb/csharp_symbols.py:340: return {"name": m.group(1), "kind": "method", "params": params, "static_ext": ext, "ret": _ret_type(rest),`

## Test files among them (0)
- none

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.
