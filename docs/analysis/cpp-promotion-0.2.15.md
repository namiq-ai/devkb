# C/C++ promotion check against SPEC-DKB-004 (2026-11-22, #123, #124)

**Result: the README row stays as it is. N1 holds; N2 fails on one C repository; F6 fails on two C++ repositories; N3 (Zephyr time) was not measured on an idle machine.**

## N1: adjudicated precision (seed 117, n=100 per repository, `bench/cpp/samples/*.jsonl`)

| Repository | Correct / 100 | 95% interval | Judged by hand | Wrong |
|---|---|---|---|---|
| autoas | 100 | 0.963-1.000 | 52 | 0 |
| cJSON | 100 | 0.963-1.000 | 0 | 0 |
| fmt | 99 | 0.946-0.998 | 60 | 1 |
| leveldb | 100 | 0.963-1.000 | 1 | 0 |
| lua | 100 | 0.963-1.000 | 5 | 0 |
| yaml-cpp | 100 | 0.963-1.000 | 16 | 0 |

Pooled by source: cpp-same-file 162/163, every other source 100% (cpp-qualified 30/30, cpp-macro 36/36, cpp-constructor 45/45, cpp-typed-receiver 85/85, cpp-unique-free 154/154). The one wrong edge: fmt `for_each_codepoint -> copy` (a 3-argument call linked to the 2-argument overload in the same file).
**Limit: the judge is not independent.** The same agent wrote the extractor, drew the sample and judged the edges; two of my first fmt verdicts were wrong and were corrected after reading the code. A second reviewer should re-judge the 134 hand-judged edges before this is quoted as a result.

The first round failed (autoas cpp-macro, Lua, fmt same-file, yaml-cpp constructor). Four extractor fixes followed, each with a test (`tests/test_cpp_macro_calls_118.py`, `tests/test_cpp_adjudicated_defects_123.py`): a macro expands only through definitions the calling file sees, and only to callees common to every visible definition; a call through a local `auto x = [` lambda is not linked; a name the file also brings in by `using` is not linked to a same-file function; `T x(*this)` is a copy. The sample was then redrawn from the fixed graph and every edge judged again, carrying over earlier verdicts for edges still present.

## N2: edge recall against compiler truth (bars: 0.80 C, 0.70 C++)

| Repository | Recall | Bar | |
|---|---|---|---|
| cJSON | 0.966 | 0.80 | met |
| lua | 0.984 | 0.80 | met |
| **autoas** | **0.747** | 0.80 | **not met** (only about 21% of its files compile for the truth) |
| leveldb | 0.847 | 0.70 | met |
| fmt | 0.703 | 0.70 | met by 0.003 |
| yaml-cpp | 0.770 | 0.70 | met |

## F6: symbol recall on each repository's own files (bar 0.95)

autoas 0.990, cJSON 1.000, lua 0.999, leveldb 0.951, **fmt 0.938, yaml-cpp 0.926** (not met).

## N3: Zephyr build time (owner bar 120 s)

Measured 109.6 s before the macro-visibility change and 133.1 s after, but the second run overlapped two benchmark batches, so it is **not a valid pass or fail**. The macro change also cut Zephyr's edges from 714,255 to 503,099 (a visibility rule, intended, not yet reviewed edge by edge) and `resolve` went from 17.5 s to 37.3 s. Re-time on an idle machine before any claim.

## What blocks promotion

1. autoas recall 0.747 < 0.80 (N2).
2. fmt 0.938 and yaml-cpp 0.926 symbol recall < 0.95 (F6).
3. N3 needs an idle-machine run, and the 30% Zephyr edge drop needs a check that it removed wrong edges, not right ones.
4. N1 needs an independent second judge.
