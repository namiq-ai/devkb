# Performance: v0.2.6 against v0.2.8 and v0.2.10 (2026-11-17)

Question: did the releases since v0.2.6 make devkb slower or heavier? This updates `performance-v0.2.6-to-main.md`, which
measured `main` before 0.2.8, with each release measured in the same run. v0.2.9 changed no performance-relevant code;
v0.2.8 and v0.2.10 bound it.

**Measured on a loaded machine.** Another service held about 9 GB of memory throughout, and the 1-minute load average
was 1.7 to 2.7 (12 cores). The numbers below compare releases with each other in this one run. They are not
absolute speeds, and not comparable with the earlier document's (v0.2.6 built click in 3.5 s here, 16.0 s there).

## Method

- `bench/perf.py`, unchanged: each repository's graph is built three times (wall time, peak memory, size on disk),
  then each command-line query runs five times (median, including interpreter start and graph load).
- Four passes, one after another, never at the same time: v0.2.10 (which picks the query targets), v0.2.6, v0.2.8,
  then v0.2.10 again to measure the noise. All passes share the same targets, interpreter (Python 3.12) and clones.
- Repositories: click (179 files), mealie (1,781), prefect (5,542), leveldb (154), fmt (148), Zephyr (70,856).
- Every build and every query succeeded in every pass.
- Raw results, targets, log and script: `bench/results/2026-11-17-perf-v0.2.10/`.

## Noise

The two v0.2.10 passes differ by **at most 2% in build time** (leveldb 6%, i.e. 0.07 s on a 1.2 s build), and peak
memory and graph size by 0–1%. Query medians differ by up to 6%, except on prefect: `symbol` by 13% and `query about` by 19% (1.65 and 1.96 s).
This is much tighter than the earlier document's 15%, so differences of a few percent are visible here that were not
visible there.

## Result

| Repository | Build s: v0.2.6 → v0.2.8 → v0.2.10 (two passes) | v0.2.6 → v0.2.10 | Peak MB | Graph MB |
|---|---|---|---|---|
| click | 3.53 → 4.01 → 3.97, 3.97 | **+12%** | 52 → 53 | 5.3 → 5.3 |
| mealie | 10.63 → 12.37 → 12.37, 12.57 | **+16 to +18%** | 85 → 85 | 15.3 → 15.3 |
| prefect | 76.6 → 88.2 → 87.3, 87.0 | **+14%** | 439 → 445–451 | 109.5 → 109.9 |
| leveldb | 1.18 → 1.24 → 1.18, 1.25 | within noise | 41 → 42 | 3.7 → 3.9 |
| fmt | 2.01 → 2.19 → 2.20, 2.21 | +9 to +10% | 51 → 52–53 | 5.5 → 5.7 |
| **Zephyr** | **116.5 → 138.5 → 139.5, 137.1** | **+18 to +20%** | **1,424 → 1,658 (+16%)** | **325 → 421 (+30%)** |

- **All of the change happened by v0.2.8. From v0.2.8 to v0.2.10 nothing moved**: every build is within the noise.
  0.2.9 and 0.2.10 (bug fixes, #104–#106, #109) cost nothing measurable.
- **Within budget:** `bench/perf_compare.py` (limits: build 1.25×, query 1.5×) passes v0.2.10 against v0.2.6 on every
  repository and query.

### Python builds: +12 to +18%, from #69

The earlier document found Python builds unchanged, but its noise was 15%. Here the noise is 2%, and the Python builds
are 12–18% slower. Timing mealie on each release puts the step between v0.2.7 and v0.2.8: v0.2.6 11.1 s, v0.2.7
11.0 s, v0.2.10 12.4 s. A profile of the mealie build (v0.2.6 against v0.2.10) attributes it to one new pass,
`build_symbols._value_refs`, which takes 7.5 of the 8.9 extra profiled seconds. Within it, 4.1 s is the recursive
walk and 2.1 s is `_bound_names`.

That pass is #69: a Python function used as a value rather than called (a callback, `sorted(key=…)`, a dispatch table)
is found, and the packs of the functions it names become Incomplete and give the line, instead of claiming that
nothing calls them. It is a deliberate correctness cost. It walks every tree three more times (calls, attributes,
then the scoped visit), so a single combined walk would likely recover part of it. Not done.

### Zephyr: +18 to +20%, as already known

This is the growth the earlier document explained: SPEC-DKB-002's C/C++ declarations, configuration-key reads and
header/Kconfig files (graph +30%, peak memory +16%). It includes the 7% saving from `1fbeda0`, which shipped in 0.2.8.
The earlier document's open point stands: a cheaper `DECLARES` encoding or lazy loading of the edge file would reduce it.

## Query latency (command line, median of five)

| | v0.2.6 | v0.2.8 | v0.2.10 (two passes) |
|---|---|---|---|
| click, mealie, leveldb, fmt: pack file / pack change / query about | 0.15–0.38 s | same ±8% | same ±8% |
| prefect: pack file / pack change / query about | 0.91 / 0.91 / 1.68 | 0.89 / 0.96 / 1.80 | 0.89–0.92 / 0.91–0.95 / 1.65–1.96 |
| **Zephyr: pack file / pack change / query about** | **1.36 / 1.35 / 5.27** | 1.54 / 1.52 / 7.07 | **1.50–1.52 / 1.49–1.54 / 7.08–7.12 (+34%)** |
| Read tools on Zephyr (v0.2.8 and v0.2.10): symbol / outline / uses | (not in v0.2.6) | 2.78 / 1.57 / 3.59 | 2.76–2.77 / 1.57–1.58 / 3.63–3.64 |

- The read tools cost 0.17–0.25 s per command-line call on small repositories, 0.73–1.03 s on prefect, and
  1.6–3.6 s on Zephyr. Almost all of that is loading the graph, which an MCP server does once.
- On Zephyr every cold command-line query reads a graph 30% larger, so `query about` is 34% slower (5.3 → 7.1 s).
  On the other repositories queries are unchanged within ±8%, about the spread between the two v0.2.10 passes.

## Summary

- **v0.2.8 → v0.2.10: no regression.**
- **v0.2.6 → v0.2.10:**
  - Python builds +12 to +18%. This is the price of #69's callback detection and is the one improvable item: one
    combined tree walk instead of three.
  - Zephyr builds +18 to +20%, peak memory +16%, graph +30%, and cold `query about` +34%. This is the known price of
    the C/C++ language profiles.
  - Small C++ repositories +0 to +10%.
  - All of it is within the perf job's limits.
