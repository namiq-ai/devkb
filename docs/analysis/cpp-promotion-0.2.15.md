# C/C++ promotion check against SPEC-DKB-004 (2026-11-23, #123, #124)

**Result: the promotion rule holds as written and the README row is ✅ Supported. One condition is still open: N1 was judged by one non-independent judge, and CI-green-on-main completes only when this branch merges.**

## Rule: N1 and N2 on every F7 repository, CI check green

| Repository | Adjudicated precision (n=100) | 95% interval | Edge recall | Bar | Symbol recall (F6, bar 0.95) |
|---|---|---|---|---|---|
| cJSON (C) | 100/100 | 0.963-1.000 | 0.966 | 0.80 | 1.000 |
| Lua (C) | 100/100 | 0.963-1.000 | 0.984 | 0.80 | 0.999 |
| autoas (C) | 100/100 | 0.963-1.000 | 0.838 | 0.80 | 0.990 |
| leveldb (C++) | 100/100 | 0.963-1.000 | 0.847 | 0.70 | 0.971 |
| fmt (C++) | 99/100 | 0.946-0.998 | 0.703 | 0.70 | 0.962 |
| yaml-cpp (C++) | 100/100 | 0.963-1.000 | 0.770 | 0.70 | 0.952 |

Every source is at or above 0.95 over the six samples (details in `docs/specs/cpp-precision-sample.md`). fmt's recall passes by 0.003.
N3 (Zephyr, the owner's 120 s bar): **113.5 s** on an otherwise idle machine, edges identical to the run before the optimisation (v0.2.11: 85.2 s).

## What changed since the 2026-11-22 check, and why

| Blocker then | Change | Effect |
|---|---|---|
| autoas recall 0.747 < 0.80 | A C library name the repository defines exactly once, in a C file with external linkage, links to that definition from callers outside host-side directories (`tools`, `test`, `util`, `example`, `sample`, `bench`, `fuzz`). autoas's `misclib.c` is its libc. **Owner-approved 2026-11-23**; ADR-DEVKB-008 §3 amended, two tests rewritten. | recall 0.747 -> 0.838, truth precision 0.991 |
| fmt 0.938, yaml-cpp 0.926 symbol recall | `~X() = default;` (in the class or `X::~X() = default;`) is a symbol; the scorer leaves definitions inside lambdas out of symbol recall on both sides (40 in fmt, reported as `truth_defs_inside_lambdas_excluded`) | fmt 0.962, yaml-cpp 0.952, leveldb 0.971 |
| Zephyr time unmeasured (133 s on a busy machine) | `_macro_calls` is cached per body: it was parsed 919,113 times | 130.7 s -> 113.5 s idle |
| CI check red | `min_calls` floors re-based to about 80% of the new counts: cJSON 3175 -> 2500, autoas 5765 -> 3590. The old floors counted wrong macro edges the adjudication removed (autoas raw precision was 0.684). | check green, 1506 tests pass |

## What the macro visibility rule does to Zephyr

`cpp-macro` edges fall from 241,020 to 30,566 (84,605 distinct edges removed). 78% of the removed edges point at four logging back ends
(`z_log_minimal_printk`, `log_frontend_stmesp_log0`, `log_frontend_stmesp_log1`, `shell_remote_cli_cbpprintf`): `LOG_ERR` expands to a different
one in each Kconfig setting, so a call to any one of them exists only in some builds. The rule keeps only calls every visible variant makes.
Not measured: that none of the removed edges is a call every build makes (the six adjudicated repositories contain no such case; Zephyr was not sampled).
The libc rule adds 8,269 `cpp-unique-free` edges on Zephyr, to its `lib/libc/minimal` functions (`memcpy` 2,853, `memset` 2,045, `strlen` 835). The call is real;
which libc supplies it is a Kconfig choice (minimal, picolibc, newlib), so those edges name the minimal one.

## Limits

- **One judge, not independent.** The agent that wrote the extractor drew the sample and judged 134 edges by hand; two of its first fmt verdicts were wrong and were corrected.
  An independent re-judgement of the 134 is owed before the precision figures are quoted outside this repository.
- **Truth builds everything freestanding**, so it counts host-side edges to `misclib.c` as correct; the host-side rule trades that measured recall (0.922 -> 0.838) for edges that are true in a real build.
- **The libc rule is a path convention** (`_HOST_DIRS`); a repository whose host programs live elsewhere gets some wrong edges to its own libc.
- Unchanged and still named in the README row: no template instantiation, no general type inference, function-pointer and ops tables unresolved.
