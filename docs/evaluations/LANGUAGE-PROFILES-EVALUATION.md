# Language profiles and boundaries: what was measured (SPEC-DKB-002, ADR-DEVKB-009)

Measured 2026-11-16 on the pinned public checkouts (cJSON, fmt, leveldb, autoas, Zephyr). Figures are from this
implementation's own runs; the compiler truth (`bench/cpp/truth_clang.py`, `quality.py`) needs `libclang`, which the
implementing session did not have, so every precision and recall below is against the independent regex truth of
`devkb.bench.cpp_truth` (`make cpp-check`), and the compiler-truth items are listed at the end as not run.

## Nothing got worse

| Repository | Edges before | Edges after | Lost | Gained | Notes |
|---|---|---|---|---|---|
| cJSON | 1,064 | 1,068 | 0 | 4 | `tests/common.h::read_file`, called from four test files that include it: true |
| leveldb | 2,107 | 2,107 | 0 | 0 | 68 edges moved from `cpp-unique-free` to `extern-c` (the C test calling `db/c.cc`) |
| fmt | 1,821 | 1,821 | 0 | 0 | |
| autoas | 3,449 | 3,475 | 0 | 26 | `extern-c` 340 = 279 C++-to-C + 61 C-to-C++, as before |
| Zephyr | 132,187 | 136,497 | 1 | 4,311 | the one lost edge is a `.c` file calling a C++ method: a C file has no receivers |

Regex truth, whole repository: cJSON precision 1.0 / recall 0.9677 (before: identical); leveldb 1.0 / 0.80 (identical).
Complete packs that miss a determinate true caller: 0 in every repository, for C and for C++.

Build time: Zephyr 92.0 s (78.6 s before; budget 120 s), cJSON 0.4 s.

## Per language (the floors in `devkb/bench/cpp_corpus.json`)

| Repository | C precision / recall | C++ precision / recall |
|---|---|---|
| cJSON | 1.0 / 0.968 | n/a |
| fmt | 1.0 / 1.0 | 0.983 / 0.60 |
| leveldb | 1.0 / 1.0 | 1.0 / 0.569 |
| autoas | 1.0 / 0.820 | 1.0 / 0.65 |
| Zephyr | 1.0 / 0.806 | 1.0 / 0.571 |

## Headers and options on Zephyr and autoas

`bench/cpp/header_counts.py` (independent regex count) against devkb's File nodes: 0 differing headers on both.
Zephyr: 5,800 tracked `.h` outside vendored paths (5,802 in all; the two others are under `subsys/ipc/open-amp/vendor/`, which the
scanner never reads), 1,637 guarded (a count of files that mention `extern "C"` and `__cplusplus` anywhere gives the owner's
1,640; three of them only name `extern "C"` in a comment or a `#define` body, which is not a guard), 0 headers with a C++
construct outside a guard (the owner's 2 are not reproduced by a count that ignores comments and `#define` bodies), 4
headers read as C++ because every includer is C++. autoas: 225 headers, 94 guarded, 21 C++, as expected.

`bench/cpp/config_counts.py`: 6,892 of 10,042 Zephyr `.c` files (68.6%) mention a `CONFIG_*` option outside comments, strings,
`#if 0` and macro bodies; devkb gives 6,889 of them (68.6%) a `READS` to a `kconfig:` key (difference 0.03 points). The
owner's 56% is not reproduced by this count; the check compares devkb with the independent count, not with 56%.

## Noise of the exported-symbol note (open question of SPEC-DKB-002)

Share of C functions whose pack carries "Complete for the languages read ... callers may exist in languages not read":
Zephyr 24.4% (26,974 of 110,751), cJSON 71.8% (798 of 1,111), fmt 33%, leveldb 13%. A C-only library whose public API is
in headers gets the note on almost every function. Narrowing it to symbols declared in a header or named by an import
record is the owner's decision.

## Not run here

- `bench/cpp/quality.py` with `by_source` and `by_language`, and `truth_clang.py` per translation-unit language and header
  inclusion graph: written, syntax-checked, not executed (no `libclang`).
- The header-language agreement with the compiler's includers (`make cpp-check ARGS="--truth-dir DIR"`): same reason.
- The `extern-c` precision floor 0.95 against compiler truth: the regex-truth precision is 1.0 on leveldb, autoas and Zephyr.
