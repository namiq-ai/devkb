# Graph baseline: what the graph of each benchmark repository looks like (2026-11-17)

This is the reference to compare a new release against. It records, for 12 repositories at pinned commits, how big the graph is (nodes and edges
by type, symbols by language, size on disk) and how long it takes to build. Use it to answer "did this release change what the graph holds, or
how much it costs?" before the release, and for degradation checks.

- devkb: `641e0671` (the tip of `main` after #96, version 0.2.7 plus the prefilter fix). Python 3.12.16. Machine: CIX P1 CP8180, 12 cores, 60 GB RAM, one build at a time.
- Data: `bench/results/2026-11-17-graph-baseline/graphs.json` (every number below is generated from it).
- Produced by `bench/graph_info.py`, compared with `bench/graph_compare.py` (below).

## How to check a release against it

```
git worktree add --detach /path/to/release-checkout <tag>        # the code under test
PERF_PYTHON=<python>  python3 bench/graph_info.py /path/to/release-checkout <label> new.json  NAME=PATH ...   # the repositories at the commits below
python3 bench/graph_compare.py bench/results/2026-11-17-graph-baseline/graphs.json new.json
```

`graph_compare.py` prints a table and exits 1 when a node or edge total, or the count of one node type or edge verb, moves by more than 2%, the graph size by more than 10%, or a build
takes more than 25% longer. `STEP` edges are left out of the comparison (see Known variation). A repository whose commit differs from the baseline's is reported as not comparable.
A moved count is not always a defect. A new feature adds edges (state it in the release notes and write a new baseline); a count that **falls** without a change meant to remove it is usually the defect.
Build times move by up to 15% between identical runs on a shared machine, so repeat a build that looks slow before acting on it; the counts do not move.

## Size and build

| Repository | What it is | Files | Nodes | Edges | Symbols | Graph MB | Build s | Symbols by language |
|---|---|---|---|---|---|---|---|---|
| click | Python CLI library (small) | 179 | 4,774 | 10,330 | 2,044 | 6.4 | 11.2 | python 2,044 |
| lattice-scan | Python tool | 175 | 3,147 | 7,672 | 1,733 | 4.8 | 6.8 | python 1,733 |
| devkb | devkb itself, at the commit pinned in `bench/repos.yaml` | 155 | 2,150 | 5,218 | 778 | 2.9 | 5.9 | python 778 |
| lnbits | Python web app (medium) | 806 | 14,126 | 35,786 | 5,730 | 20.6 | 30.1 | python 5,579, none 151 |
| mealie | Python web app (medium) | 1,781 | 22,937 | 47,041 | 5,629 | 26.2 | 76.1 | python 4,996, none 633 |
| dispatch | Python web app (large) | 1,569 | 11,561 | 21,135 | 4,127 | 13.7 | 31.4 | python 4,005, none 122 |
| prefect | Python platform (largest Python) | 5,542 | 91,299 | 186,592 | 41,056 | 129.2 | 207.0 | python 38,097, none 2,959 |
| cJSON | C library | 229 | 1,567 | 2,540 | 1,184 | 2.5 | 1.0 | c 1,170, python 14 |
| fmt | C++ library | 148 | 4,046 | 6,006 | 3,167 | 5.7 | 2.4 | cpp 3,037, python 112, c 18 |
| leveldb | C++ library | 154 | 2,222 | 4,327 | 1,833 | 3.8 | 1.3 | cpp 1,818, c 15 |
| autoas | AUTOSAR stack, C with C++ and Python | 1,004 | 6,443 | 10,718 | 5,665 | 10.4 | 6.6 | c 2,976, cpp 1,514, python 1,175 |
| zephyr | RTOS: C, Kconfig and devicetree (largest) | 70,856 | 251,805 | 482,710 | 147,374 | 425.0 | 140.8 | c 137,342, python 9,647, cpp 245 |
| **Total** | | 82,598 | 416,077 | 820,075 | 220,320 | 651.2 | 521 | |

`none` is a symbol with no recorded language (probably JavaScript or web assets; not checked).

## Edges by verb

| Repository | DEFINED_IN | CALLS | DECLARES | TOUCHES | READS | LOGS | TESTED_BY | STEP | GROUPS |
|---|---|---|---|---|---|---|---|---|---|
| click | 2,672 | 3,430 | 0 | 1,645 | 12 | 9 | 1,378 | 0 | 995 |
| lattice-scan | 2,476 | 2,669 | 0 | 929 | 13 | 0 | 545 | 503 | 229 |
| devkb | 980 | 1,549 | 0 | 1,665 | 24 | 0 | 219 | 412 | 209 |
| lnbits | 7,318 | 8,754 | 165 | 7,679 | 25 | 488 | 2,756 | 4,400 | 1,418 |
| mealie | 7,703 | 6,704 | 48 | 18,878 | 6 | 62 | 2,471 | 1,837 | 4,473 |
| dispatch | 4,562 | 3,932 | 54 | 4,058 | 9 | 455 | 695 | 3,280 | 1,822 |
| prefect | 60,230 | 49,117 | 44 | 34,062 | 93 | 310 | 19,764 | 5,743 | 7,130 |
| cJSON | 1,452 | 1,072 | 0 | 0 | 0 | 0 | 0 | 12 | 1 |
| fmt | 3,857 | 1,929 | 0 | 148 | 1 | 0 | 0 | 31 | 1 |
| leveldb | 2,065 | 2,107 | 0 | 154 | 0 | 0 | 0 | 0 | 1 |
| autoas | 5,668 | 4,686 | 0 | 0 | 26 | 47 | 2 | 166 | 1 |
| zephyr | 157,999 | 149,720 | 82,261 | 0 | 52,152 | 36,494 | 1,390 | 1,967 | 1 |

Other verbs, all repositories: MERGES 15,073, RAISES 6,352, DEPLOYS 65, CLOSES 39, TAGS 11, CALLS_API 8, REGISTERED_ON 8.

## Nodes by type

| Repository | Symbol | File | ConfigKey | TestCase | ErrorSignature | Commit | PullRequest |
|---|---|---|---|---|---|---|---|
| click | 2,044 | 241 | 6 | 628 | 85 | 995 | 43 |
| lattice-scan | 1,733 | 179 | 12 | 743 | 76 | 229 | 125 |
| devkb | 778 | 702 | 15 | 202 | 7 | 209 | 49 |
| lnbits | 5,730 | 893 | 145 | 1,585 | 1,247 | 1,418 | 1,292 |
| mealie | 5,629 | 2,315 | 46 | 2,064 | 295 | 4,473 | 3,775 |
| dispatch | 4,127 | 1,042 | 34 | 435 | 429 | 1,822 | 1,819 |
| prefect | 41,056 | 7,666 | 90 | 19,120 | 1,712 | 7,130 | 7,084 |
| cJSON | 1,184 | 101 | 0 | 268 | 1 | 1 | 0 |
| fmt | 3,167 | 148 | 1 | 690 | 26 | 1 | 0 |
| leveldb | 1,833 | 154 | 0 | 232 | 0 | 1 | 0 |
| autoas | 5,665 | 660 | 17 | 3 | 74 | 1 | 0 |
| zephyr | 147,374 | 31,294 | 36,719 | 10,623 | 25,552 | 1 | 0 |

Other types, all repositories: WorkUnit 13,764, Flow 1,730, Endpoint 1,046, Component 65, Spec 45, Ticket 39, Repository 12, Release 11.

## Pinned commits

The numbers are only comparable at these commits (the entries in `bench/repos.yaml` and `devkb/bench/cpp_corpus.json`). `commits in clone` explains why history nodes differ: the C and C++ corpus clones are shallow.

| Repository | Commit | Commits in clone |
|---|---|---|
| click | `e38188e9e205005d5af5f9e59df51904c984586a` | 3,413 |
| lattice-scan | `17e2aefd7f7b6b7c7d68a6a3538bc51cebf7c6f5` | 229 |
| devkb | `b6a2c9ca10ea50063fda2b8552a038dd27f2b1df` | 2 |
| lnbits | `c8d4701304888696768cbdb2424db4d8b227128e` | 7,401 |
| mealie | `a083a4dd6e46a91d19666399cacac77a923bd32d` | 5,937 |
| dispatch | `dd2837e82a0bf5565b1b4b4b91ea30b7262d4061` | 5,279 |
| prefect | `c12b3322560bee718479da8968e7af017df2ea33` | 22,492 |
| cJSON | `6d9f2443ab071f86e5d9b43025a40929ec41c46c` | 1 |
| fmt | `57f1b5930dc2906875534a15c209e1c39eda59ad` | 1 |
| leveldb | `29465588d3dfdc80fba5e198037582b8fdb5dd60` | 1 |
| autoas | `cc3709675ac30f7539c0710dfec6d579a5235841` | 1 |
| zephyr | `7cd4b562b30a9bcd76a7288ad90d5e71dd6f87d2` | 1 |

## What to read from it

- **Zephyr is 60% of the nodes, 59% of the edges and 65% of the size** (251,805 of 416,077 nodes, 482,710 of 820,075 edges, 425 of 651 MB); a regression that matters for large repositories shows there first.
- **Where the C/C++ language-profile edges are:** `DECLARES` (82,261), `READS` (52,152) and `ConfigKey` nodes (36,719) are almost all Zephyr's; autoas has 26 `READS` and 17 `ConfigKey`.
- **History nodes** (`Commit`, `PullRequest`, `TOUCHES`, `GROUPS`) exist only where the clone has history: the Python benchmarks have hundreds to thousands, the C and C++ clones have one commit and none.
- **`CALLS` edges per symbol** range from 0.6 (fmt) to 2.0 (devkb) with no pattern by language (Python 0.95 to 2.0, C and C++ 0.6 to 1.15).

## Known variation

- **`STEP` edges** (flow tracing, `touch-point-bfs`) vary between builds of the same code: about 1,300 of Zephyr's 1,967 differ between any two builds. With `PYTHONHASHSEED=0` every other file is byte-identical. The comparison script ignores them.
- **Build time** varies by up to 15% between identical runs and with the machine's load; this baseline was measured with nothing else running.
- **Size on disk** is the sum of the `.devkb` files (JSON lines); it follows the node and edge counts exactly.
- The first version of this baseline has no memory column: peak memory of a build is in `bench/perf.py` runs (`docs/analysis/performance-v0.2.6-to-main.md`: Zephyr 1.7 GB).

## Relation to the other checks

`bench/perf.py` and the `perf` job in `bench.yml` compare build and query time against the previous release on two small repositories on every pull request; this baseline adds what the graph holds on twelve, and is run by hand before a release.
