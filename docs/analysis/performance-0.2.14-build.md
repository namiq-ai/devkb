# Build and query baseline, v0.2.14, one repository per language (#370)

`bench/perf_release.py v0.2.13 v0.2.14 NAME=PATH ...` (2026-11-22), three timed passes in one run: v0.2.14, v0.2.13, v0.2.14 again. Each metric is compared with the gap between
the two v0.2.14 passes: a change no larger than that gap is marked `within noise` in the raw report (`~/.cache/devkb/perf-release/v0.2.13-vs-v0.2.14/compare.md`).
The machine was not idle (load average 1.64, 1.70, 1.79 before the three passes, the script's limit being 2.0), so a change of a few percent in a build of one or two seconds is
not a finding.

## The baseline (v0.2.14) and what changed since v0.2.13

| repository | language | build s (v0.2.14, 2 passes) | peak MB | graph MB | `pack file` s | `symbol` s | `uses` s | build change vs v0.2.13 |
|---|---|---|---|---|---|---|---|---|
| click | Python | 4.8 (old 4.6) | 54 | 5.4 | 0.21 | 0.19 | 0.24 | +4% |
| prefect | Python | 104.9 (old 103.33) | 463 | 109.4 | 0.96 | 0.89 | 1.11 | +2% |
| leveldb | C++ | 1.5 (old 1.41) | 46 | 4.4 | 0.18 | 0.18 | 0.19 | +6% |
| fmt | C++ | 2.6 (old 2.46) | 58 | 6.3 | 0.23 | 0.20 | 0.21 | +5% |
| zephyr | C | 171.0 (old 172.12) | 2315 | 592.1 | 1.79 | 3.93 | 4.80 | -1% |
| mediatr | C# | 1.5 (old 1.34) | 37 | 2.7 | 0.19 | 0.17 | 0.21 | +13% |
| mealie | Python + TypeScript/JS (stand-in) | 15.0 (old 14.09) | 95 | 16.5 | 0.36 | 0.25 | 0.34 | +6% |

Query medians are seconds for one call over five. Pins: click e38188e, prefect c12b332, mealie a083a4d (`bench/repos.yaml`); leveldb 2946558, fmt 57f1b59, Zephyr 7cd4b56
(`devkb/bench/cpp_corpus.json`); MediatR 1fad4c7 (`bench/languages.yaml`).

## Reading it

- **Nothing moved beyond what the machine allowed.** Build time: Zephyr -1%, prefect +2%, click +4%, fmt +5%, leveldb +6%, mealie +6%, MediatR +13%. The largest is MediatR's, 1.34 s to
  1.5 s, which is 0.14 s and about the size of the gap between the two v0.2.14 passes on a loaded machine. Peak memory, graph size and every query median are within 3% except
  `pack file` on click (+12%, 0.19 s to 0.21 s) and `symbol` on MediatR (+10%, 0.16 s to 0.17 s): tenths of a second.
- **Zephyr is 171 s here, and 115.9 s in the extractor-only timing of #405.** This check times the whole `devkb build` (symbols, the process graph, the index), not `build_symbols.extract` alone. Both are right for what they time; they
  are not comparable with each other. Against the v0.2.11 build, only the extractor-only figure exists (87.0 s, +33% for the 0.2.15 candidate; #405).
- **TypeScript and JavaScript have no corpus yet.** SPEC-DKB-008's story 1 (the measurement and its repositories) is open, so the stand-in is mealie, a Python application with a Vue frontend (328 `.ts`/`.js`
  files). Replace it when story 1 pins its repositories.
- **C# is MediatR** (the smallest repository `bench/languages.yaml` pins); Jellyfin and EF Core are in the CI check but too slow for a release pass.

## How the next release uses it

`perf_release.py v0.2.14 NEW <the same seven repositories>` and compare with this table: the proposed target (the release owner confirms it) is no build time, peak memory or query median beyond noise, except
where a ticket says why. The 0.2.14 to 0.2.15 run is recorded in the section below. #289's fix is measured against this table on the same repositories and by its own count-based fixture
(`tests/test_build_same_name_linear_289.py`: 640,000 reach tests become 800).
