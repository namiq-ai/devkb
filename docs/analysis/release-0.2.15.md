# Release 0.2.15: C/C++ Supported, TypeScript spans, and a benchmark that records what an agent could use (2026-11-23)

61 tickets are closed in milestone 0.2.15; #313 (the TypeScript/JavaScript epic) moved to 0.2.16 by the owner after its first slice (#418) shipped.
27 commits since v0.2.14. Raw data and scripts are in the files named below; nothing here is quoted from memory.

## Summary

- **C and C++ reach ✅ Supported** (#123, #124, PR #421). SPEC-DKB-004's rule (N1 and N2 on every F7 repository, CI green) holds on six pinned repositories:
  adjudicated precision 599/600 (95% lower bounds 0.946 to 0.963); edge recall cJSON 0.966, Lua 0.984, autoas 0.838 (bar 0.80), leveldb 0.847,
  fmt 0.703, yaml-cpp 0.770 (bar 0.70); symbol recall 0.952 to 1.000; Zephyr builds in 113.5 s on an idle machine (owner bar 120 s, v0.2.11 85.2 s).
  The first adjudication round failed on macro, same-file and constructor edges; four extractor fixes followed (macro visibility and variant
  intersection, local lambdas, `using` names, copy of `*this`), then the samples were redrawn and re-judged. Details: `docs/analysis/cpp-promotion-0.2.15.md`,
  `docs/specs/cpp-precision-sample.md`, `docs/analysis/cpp-extractor-0.2.15.md`.
- **Where the C/C++ result is weaker than it looks.** One judge wrote the extractor, drew the sample and judged all 134 hand-checked edges; an independent
  re-judgement is owed. Zephyr's `cpp-macro` edges fell from 241,020 to 30,566 (logging back ends that differ per Kconfig) and were not sampled. A C library
  name the repository defines once now links to that definition from firmware code, a directory convention (ADR-DEVKB-008 §3 amended, owner-approved).
- **TypeScript and TSX symbols have their real start and end line** (#418, PR #419): `outline` and `symbol --source` are exact. A masker for comments, strings,
  nested template literals, regex literals and JSX text carries it; every defect the reviews found has a test.
- **The benchmark records which devkb entry points an agent could use** (#420): a `both` arm (shell, hook and tool) and a per-run `entry_points` record;
  a ticket's location can be withheld even when it is written inline (#386, PR #417); `pack file` lists the files that run a module by name (#389).
- **Agents still almost never query devkb.** Hidden-location batches of 7 runs per arm: #386 none 5/7, main 6/7, bothuser 7/7 acceptance (cost $0.148,
  $0.165, $0.169; 0 devkb queries); #418 all arms 7/7 (cost $0.440, $0.420, $0.416; 1 query each in main and bothuser). Across the two, the tool entry
  point made 1 query in 14 runs and was no cheaper: it stays off. Differences at n=7 are within noise. Usage by period: `docs/analysis/devkb-usage-0.2.15-by-period.md`.

## Hook and read tools

Searches piped into a bare `head` or `tail` are answered (#393); a search of a changed file's neighbours is answered when no changed file mentions the name
(#409, #410); `symbol` puts the match spelled as the query first (#372); `devkb build --allow-foreign-checkout` (#383); aliases and `runpy` dependents in
`pack file` (#382); `pack error` precision (#399) and tuple-unpack attribution (#400); a workflow router, off by default, and quality benchmarks QB1 to QB5 (#401, #403).

## Measurement mistakes found and fixed on the way

- A benchmark work directory under `~/.claude` made the permission checker refuse every edit, invalidating the runs; work directories live under `~/.cache` now.
- A one-arm batch made its own base suite red because `POLICY_*` leaked into the checkout's suite run (`suite_env()`).
- The C++ scorer counted a call to any overload of a name as wrong when the compiler picked another; it now maps a node to every overload (#406).
- A stale monitor shell stalled the next batch for 10 hours; found by reading its process list, not by a failure.
- My own cost estimate for the 7-run experiment was low (about $8, not $4 to $6 for #418); corrected before it ran.

## Performance (v0.2.14 against main, `bench/perf_release.py`)

Run: `bench/perf_release.py v0.2.14 main` (main at 922b879), passes NEW, OLD, NEW; load before the passes 2.00, 1.85, 1.95 (the machine was not idle: other `devkb build` processes ran, so the load gate of 2.0 was met, not passed with room). Full table: `~/.cache/devkb/perf-release/v0.2.14-vs-0.2.15/v0.2.14-vs-main/compare.md`. **The check found changes beyond the noise pass; the release rule (docs/RELEASING.md step 0) requires a ticket for each, so before the tag:**

| Repository | Build s (old, new a/b) | Change | Other changes beyond noise | Ticket |
|---|---|---|---|---|
| click (Python) | 4.74, 5.84 / 5.71 | **+22%** | `pack file` +22%, `pack change` +14% | #432, #433 |
| prefect (Python) | 105.4, 129.5 / 125.6 | **+21%** | `pack file` +28%, `pack change` +22%, peak memory +3% | #432, #433 |
| mealie (Python + TS) | 15.1, 18.5 / 17.9 | **+20%** | `pack file` and `pack change` +28% | #432, #433 |
| leveldb (C++) | 1.49, 1.68 / 1.69 | +13% | peak +7%, graph +9%, `symbol` and `uses` +15% | #435 |
| fmt (C++) | 2.61, 2.91 / 2.91 | +11% | peak +7%, graph +11% | #435 |
| zephyr (C) | 172.5, 173.1 / 168.7 | -1% (within noise) | `pack change` **+48%**, peak +9%, `outline` +10%; graph **-22%**, `query about` -21% | #434 |
| mediatr (C#) | 1.48, 1.45 / 1.49 | -1% (within noise) | `symbol` +19% | #435 |

Cause found for the Python build: `_module_runs` (#389) does five AST walks per file for a result only a file naming `run_module` or `"-m"` can have (1.85 s of the 2.55 s profiled increase on click). PR #441 skips it for other files: click extract 3.2 s (v0.2.14), 3.8 s (main), 3.5 s (fix); the remaining +9% is spread over small new passes. `pack file` pays `_named_by_path` (+0.079 s) and an import of `build_symbols` (+0.072 s) on a 0.4 s call (#433). Two measures of Zephyr differ and must not be mixed: the harness's whole `devkb build` is 172 s for both versions; the 120 s bar of #405 was met with `extract` alone (113.5 s).

## Not done, and carried to 0.2.16

Filed for 0.2.16 on 2026-11-23: hook answers (#422 question by intent, #423 candidate lists, #424 partial answers, #426 text searches), pre-edit (#425 pack keeps its Incomplete note, #427 measured effect), graph (#428 constants and keys in `symbol`), staleness (#429 detached refresh; #411 incremental update), telemetry (#430 hook commit per row, #431 `Read` hints), performance (#432 Python build, #433 `pack file`, #434 Zephyr, #435 C/C++ and C#), documentation (#436 commands that exist), C/C++ caveats (#437 independent re-judgement, #438 removed Zephyr macro edges, #439 host directories), harness (#440 guards). #313 (TypeScript/JavaScript Supported) moved to 0.2.16 by the owner.

#313 (TypeScript/JavaScript Supported; SPEC-DKB-008 is still `proposed`); an independent re-judgement of the C/C++ hand verdicts; a sample of Zephyr's removed macro
edges; #411 (incremental graph update); the harness change to build the graph after the policy commit (not filed).
