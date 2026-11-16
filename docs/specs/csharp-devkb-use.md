# devkb used to build its own C# support (#32)

The packs below were taken from devkb's graph of its own repository before the change, and decided where the
change went and which tests had to keep passing. Kept as evidence for the spec (SPEC-DEVKB-CSHARP §6).

What they changed:

- **`build_symbols.py` file pack**: `extract` is called from 8 files, so C# goes in as one call at its end
  (`csharp_symbols.add_to_graph`) rather than a new branch inside the Python walk.
- **`test_discovery.py` file pack** and **`list_test_files` refactor pack**: the callers that list test files had to
  keep their Python behaviour; `.cs` support is added beside `_PY_TEST`, not by widening it.
- **`is_test_path` refactor pack**: every pack and the MCP server classify test files through it, so the C# rule
  lives there once and every pack lists C# test files without its own code path (F5).
- A finding on the way: the graph flagged `devkb/extractors/test_inventory.py` as a test file (its name matched
  `test_*`). Not changed here; noted for a follow-up.


---

## Graph pack: before editing `devkb/build_symbols.py`

Built from the dev-process graph at commit `0657994305`. None of the files below has changed since; the line numbers are current.

## Functions other files call (17 of 60)
- `extract` — 8 file(s): `tests/test_devkb_audit_efficiency_odsf314.py:81: g = build_symbols.extract(tmp_path)` and 7 more file(s)
- `_decorator_route` — 2 file(s): `tests/test_devkb_coverage_classes_odsf313.py:120: assert _decorator_route(dec('public_router.post("/token")')) == ("POST", "/token")` and 1 more file(s)
- `_list_python_files` — 2 file(s): `devkb/extractors/symbol_tests.py:59: register_reexports(symbols_by_file, collect_reexports(ctx.repo_root, _list_python_files(ctx.repo_root)))` and 1 more file(s)
- `load_cache` — 2 file(s): `devkb/build.py:165: build_symbols.load_cache(ctx),` and 1 more file(s)
- `_calls_in_body` — 1 file(s): `devkb/extractors/symbol_tests.py:40: pairs = set(_calls_in_body(node))`
- `_import_descriptors` — 1 file(s): `devkb/extractors/symbol_tests.py:74: receivers, bare = _import_targets(_import_descriptors(tree), rel)`
- `_import_targets` — 1 file(s): `devkb/extractors/symbol_tests.py:74: receivers, bare = _import_targets(_import_descriptors(tree), rel)`
- `_imports` — 1 file(s): `devkb/extractors/symbol_tests.py:69: imported = _imports(tree)`
- `_module_paths` — 1 file(s): `devkb/extractors/symbol_tests.py:111: for guess in _module_paths(dotted_module):`
- `_odoo_route` — 1 file(s): `tests/test_devkb_coverage_odsf304.py:81: assert build_symbols._odoo_route(_decorator("@other.route('/e')")) is None`
- `_odoo_xml_symbols` — 1 file(s): `tests/test_devkb_coverage_odsf304.py:91: found = build_symbols._odoo_xml_symbols(root)["addon/views/a.xml"]`
- `_py_literals` — 1 file(s): `devkb/extractors/symbol_tests.py:75: literals = _py_literals(tree)`
- `_resolve_cross_file_symbol` — 1 file(s): `devkb/extractors/symbol_tests.py:83: hit = next((h for h in (_resolve_cross_file_symbol(m, rel, short, symbols_by_file) for m in modules) if h), None)`
- `_resolve_via_literals` — 1 file(s): `devkb/extractors/symbol_tests.py:95: hit = _resolve_via_literals(literals, short, symbols_by_file)`
- `build` — 1 file(s): `tests/test_devkb_pull_requests_adr007.py:75: build_symbols.build(str(root))`
- `collect_reexports` — 1 file(s): `devkb/extractors/symbol_tests.py:59: register_reexports(symbols_by_file, collect_reexports(ctx.repo_root, _list_python_files(ctx.repo_root)))`
- `register_reexports` — 1 file(s): `devkb/extractors/symbol_tests.py:59: register_reexports(symbols_by_file, collect_reexports(ctx.repo_root, _list_python_files(ctx.repo_root)))`

## Files that depend on it (13)
- `devkb/build.py`
- `devkb/extractors/symbol_tests.py`
- `tests/test_devkb_audit_efficiency_odsf314.py`
- `tests/test_devkb_bl_baseline_symbols_odsf042.py`
- `tests/test_devkb_bl_containment_errors_criticality_odsf043.py`
- `tests/test_devkb_bl_crossfile_ts_api_odsf043.py`
- `tests/test_devkb_call_resolution_odsf305.py`
- `tests/test_devkb_coverage_classes_odsf313.py`
- `tests/test_devkb_coverage_odsf304.py`
- `tests/test_devkb_pull_requests_adr007.py`
- `tests/test_devkb_submodules_odsf312.py`
- `tests/test_devkb_typed_calls_odsf312.py`
- `tests/test_reexports_module_calls.py`

## Tests that exercise it, directly or through callers (13)
- `tests/test_devkb_audit_efficiency_odsf314.py` — `tests/test_devkb_audit_efficiency_odsf314.py:81: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_baseline_symbols_odsf042.py` (+5 more tests) — `tests/test_devkb_bl_baseline_symbols_odsf042.py:133: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_containment_errors_criticality_odsf043.py` (+12 more tests) — `tests/test_devkb_bl_containment_errors_criticality_odsf043.py:146: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_crossfile_ts_api_odsf043.py` (+5 more tests) — `tests/test_devkb_bl_crossfile_ts_api_odsf043.py:58: g = build_symbols.extract(tmp_path)`
- `tests/test_devkb_bl_linkage_workunits_odsf042.py` (+3 more tests) — `tests/test_devkb_bl_linkage_workunits_odsf042.py:52: g = symbol_tests.extract(ctx, graph)`
- `tests/test_devkb_builder_checkout_odsf104.py` (+1 more tests) — `tests/test_devkb_builder_checkout_odsf104.py:135: build_mod.build("X", allow_foreign_checkout=False)`
- `tests/test_devkb_call_resolution_odsf305.py` (+8 more tests) — `tests/test_devkb_call_resolution_odsf305.py:53: assert ("pkg/run.py::go", "pkg/store.py::save_record") in _calls(build_symbols.extract(root))`
- `tests/test_devkb_coverage_classes_odsf313.py` (+6 more tests) — `tests/test_devkb_coverage_classes_odsf313.py:43: g = build_symbols.extract(_repo(tmp_path))`
- `tests/test_devkb_coverage_odsf304.py` (+2 more tests) — `tests/test_devkb_coverage_odsf304.py:81: assert build_symbols._odoo_route(_decorator("@other.route('/e')")) is None`
- `tests/test_devkb_pull_requests_adr007.py` (+1 more tests) — `tests/test_devkb_pull_requests_adr007.py:75: build_symbols.build(str(root))`
- `tests/test_devkb_submodules_odsf312.py` — `tests/test_devkb_submodules_odsf312.py:36: files = build_symbols._list_python_files(product)`
- `tests/test_devkb_typed_calls_odsf312.py` — `tests/test_devkb_typed_calls_odsf312.py:35: g = build_symbols.extract(tmp_path)`
- `tests/test_reexports_module_calls.py` (+3 more tests) — `tests/test_reexports_module_calls.py:42: g = build_symbols.extract(root)`

Run: `python3 -m pytest tests/test_devkb_audit_efficiency_odsf314.py tests/test_devkb_bl_baseline_symbols_odsf042.py tests/test_devkb_bl_containment_errors_criticality_odsf043.py tests/test_devkb_bl_crossfile_ts_api_odsf043.py tests/test_devkb_bl_linkage_workunits_odsf042.py tests/test_devkb_builder_checkout_odsf104.py tests/test_devkb_call_resolution_odsf305.py tests/test_devkb_coverage_classes_odsf313.py tests/test_devkb_coverage_odsf304.py tests/test_devkb_pull_requests_adr007.py tests/test_devkb_submodules_odsf312.py tests/test_devkb_typed_calls_odsf312.py tests/test_reexports_module_calls.py -q`

## Coverage
**Incomplete: 30 call site(s) under this name could not be attributed.** 19 symbols share the name, so most may be calls to the others. Search only these files for them: `devkb/github.py`, `devkb/build_symbols.py`, `devkb/extractors/members.py`, `devkb/bench/truth_check.py`, `devkb/bench/oco_tasks.py`, `devkb/bench/workflow_tasks.py`, `devkb/edge_truth.py`, `devkb/process_api.py`, `devkb/test_discovery.py`.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: before editing `devkb/test_discovery.py`

Built from the dev-process graph at commit `0657994305`. None of the files below has changed since; the line numbers are current.

## Functions other files call (2 of 2)
- `list_test_files` — 6 file(s): `devkb/coverage.py:96: for rel in list_test_files(ctx.repo_root):` and 5 more file(s)
- `tests_in_file` — 3 file(s): `devkb/coverage.py:97: for _name, line in tests_in_file(ctx.repo_root, rel):` and 2 more file(s)

## Files that depend on it (6)
- `devkb/coverage.py`
- `devkb/extractors/files_tests.py`
- `devkb/extractors/symbol_tests.py`
- `devkb/extractors/test_inventory.py`
- `tests/test_devkb_coverage_odsf304.py`
- `tests/test_devkb_submodules_odsf312.py`

## Tests that exercise it, directly or through callers (8)
- `devkb/extractors/test_inventory.py` (+1 more tests) — `devkb/extractors/test_inventory.py:22: for rel in list_test_files(ctx.repo_root, ctx.tests_dir):`
- `tests/test_devkb_bl_linkage_workunits_odsf042.py` (+3 more tests) — `tests/test_devkb_bl_linkage_workunits_odsf042.py:52: g = symbol_tests.extract(ctx, graph)`
- `tests/test_devkb_builder_checkout_odsf104.py` (+1 more tests) — `tests/test_devkb_builder_checkout_odsf104.py:135: build_mod.build("X", allow_foreign_checkout=False)`
- `tests/test_devkb_call_resolution_odsf305.py` — `tests/test_devkb_call_resolution_odsf305.py:78: graph = build_symbols.extract(root)`
- `tests/test_devkb_coverage_odsf304.py` (+3 more tests) — `tests/test_devkb_coverage_odsf304.py:53: found = test_discovery.list_test_files(root)`
- `tests/test_devkb_files_tests_odsf032.py` (+2 more tests) — `tests/test_devkb_files_tests_odsf032.py:142: g = files_tests.extract(ctx, tickets_graph)`
- `tests/test_devkb_pull_requests_adr007.py` — `tests/test_devkb_pull_requests_adr007.py:75: build_symbols.build(str(root))`
- `tests/test_devkb_submodules_odsf312.py` — `tests/test_devkb_submodules_odsf312.py:38: assert "oco-edge/tests/test_probe.py" in test_discovery.list_test_files(product)`

Run: `python3 -m pytest devkb/extractors/test_inventory.py tests/test_devkb_bl_linkage_workunits_odsf042.py tests/test_devkb_builder_checkout_odsf104.py tests/test_devkb_call_resolution_odsf305.py tests/test_devkb_coverage_odsf304.py tests/test_devkb_files_tests_odsf032.py tests/test_devkb_pull_requests_adr007.py tests/test_devkb_submodules_odsf312.py -q`

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/test_discovery.py::list_test_files`

Built from the dev-process graph at commit `0657994305`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/test_discovery.py:30: def list_test_files(repo_root: Path, tests_dir: Path | None = None) -> list[str]:`.

## Files with a direct caller (6, tests included)
- `devkb/coverage.py` — `devkb/coverage.py:96: for rel in list_test_files(ctx.repo_root):`
- `devkb/extractors/files_tests.py` — `devkb/extractors/files_tests.py:188: files=[ctx.repo_root / rel for rel in list_test_files(ctx.repo_root, ctx.tests_dir) if rel.endswith(".py")],`
- `devkb/extractors/symbol_tests.py` — `devkb/extractors/symbol_tests.py:62: for py in (ctx.repo_root / rel for rel in list_test_files(ctx.repo_root, ctx.tests_dir) if rel.endswith(".py")):`
- `devkb/extractors/test_inventory.py` — `devkb/extractors/test_inventory.py:22: for rel in list_test_files(ctx.repo_root, ctx.tests_dir):`
- `tests/test_devkb_coverage_odsf304.py` — `tests/test_devkb_coverage_odsf304.py:53: found = test_discovery.list_test_files(root)`
- `tests/test_devkb_submodules_odsf312.py` — `tests/test_devkb_submodules_odsf312.py:38: assert "oco-edge/tests/test_probe.py" in test_discovery.list_test_files(product)`

## Test files among them (3)
- `devkb/extractors/test_inventory.py`
- `tests/test_devkb_coverage_odsf304.py`
- `tests/test_devkb_submodules_odsf312.py`

(The defining file `devkb/test_discovery.py` is not counted as a caller.)

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.

---

## Graph pack: changing the signature of `devkb/process_api.py::is_test_path`

Built from the dev-process graph at commit `0657994305`. None of the files below has changed since; the line numbers are current.

Defined at `devkb/process_api.py:89: def is_test_path(path: str) -> bool:`.

## Files with a direct caller (3, tests included)
- `devkb/packs.py` (+3 more) — `devkb/packs.py:305: if i is not None and "." not in qual and not is_test_path(path) and self.idx.props[i].get("kind") == "function":`
- `devkb/process_api.py` (+13 more) — `devkb/process_api.py:806: return sum(1 for c in set(self.idx.sources("CALLS", i)) if not is_test_path(self._key(c).split("::")[0]))`
- `tests/test_module_truth_routes.py` — `tests/test_module_truth_routes.py:61: assert is_test_path("tests/fixtures/fixture_users.py") and is_test_path("pkg/tests/conftest.py")`

## Test files among them (1)
- `tests/test_module_truth_routes.py`

## Coverage
**Complete.** Every call site under these names was attributed to its target; nothing else calls them.

---
This pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the answer is incomplete.
