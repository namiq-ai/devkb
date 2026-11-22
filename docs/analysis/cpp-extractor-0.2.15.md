# The C/C++ extractor tickets of 0.2.15, measured against the compiler (2026-11-22)

Tickets: #95, #119, #121, #122, #145, #146, #244, #289, #290, #291, #292, #311. Branch `fix/cpp-extractor-145-146-95`, 12 commits on `release/0.2.15`.
Nothing here is closed on GitHub; this note is what to check before closing.

## How the compiler truth was run (so it can be repeated)

`bench/cpp/truth_clang.py` needs libclang. The `libclang` wheel was installed into the repository venv (`uv pip install --python .venv/bin/python libclang`,
18.1.1), which also un-skips the compiler-based tests (the suite is 1278 passed, 0 skipped). The wheel ships no builtin headers; gcc's are used:

```
GI=$(gcc -print-file-name=include)
truth_clang.py ~/.cache/devkb/cpp-corpus/leveldb OUT.json --std c++17 -I include -I . -I $GI \
  -D LEVELDB_PLATFORM_POSIX=1 -D LEVELDB_IS_BIG_ENDIAN=0 -D HAVE_SNAPPY=0 -D HAVE_CRC32C=0 -D HAVE_ZSTD=0 -D HAVE_FDATASYNC=1 -D HAVE_FULLFSYNC=0 -D HAVE_O_CLOEXEC=1
truth_clang.py .../fmt        OUT.json --std c++17 -I include -I $GI
truth_clang.py .../yaml-cpp   OUT.json --std c++17 -I include -I src -I $GI
quality.py WORKTREE REPO OUT.json [--examples]      # then split_wrong.py WORKTREE REPO OUT.json QUALITY_EXAMPLES.json
```

Translation units that need gtest, gmock or sqlite sources absent from the checkouts do not compile and are "not measured" by design (SPEC F1):
leveldb 36 of 77, fmt 25 of 48, yaml-cpp 120 of 160. Every figure below is therefore about the code that compiles, not the whole repository.

## Results (compiler truth; before = `main` at f1c1502 unless stated)

| repository | measure | before | now |
|---|---|---|---|
| leveldb | edge recall | 0.662 | **0.800** |
| leveldb | missed method edges (bar: 100 or fewer) | 177 | **88** |
| leveldb | missed constructor edges | 268 | 93 (65% found) |
| leveldb | typed-receiver edges, correct / wrong | 577 / 12 | 670 / 12 |
| leveldb | raw edge precision | 0.986 | 0.950 |
| leveldb | symbol recall (by name, scorer) | 0.953 | 0.953 |
| fmt | symbol recall (definitions found, lambdas excluded) | 0.787 | **0.953** |
| fmt | edge recall | 0.521 | 0.575 |
| yaml-cpp | symbol recall (same metric) | 0.955 | 0.955 |
| yaml-cpp | edge recall | 0.519 | 0.596 |
| Zephyr | build, seconds (alternating, idle machine) | 108.2 (v0.2.14) | 117.9, **+9.0%** (+7.6% over `main` as merged) |

## What the numbers do and do not say

- **Raw precision falls, and most of the fall is the scoring convention.** The graph keeps one node for all overloads of a name; the truth has one definition per
  overload, so an edge to the merged node is "wrong" when the truth records a different overload. `split_wrong.py` on leveldb: of 87 wrong edges, 60 are such
  target picks, 14 are truth gaps (template bodies), and the rest are a text heuristic that cannot see `T x(args)`. Checked by hand on 4 of the flagged yaml-cpp
  edges: all four have the construction written in the caller. On fmt, 361 of 400 sampled wrong edges are truth gaps and 3 are flagged as devkb's own.
  Raw precision is still the number a reader will quote: leveldb 0.950, yaml-cpp 0.804 to 0.762, fmt 0.387 to 0.344.
- **#119 is not at its bar.** The ticket asks for 80% of the missed constructor edges; 65% are found. Not covered: copy-initialisation (`Status s = f();`),
  implicit conversions, and member or base initialisers the scanner cannot type. Copy-initialisation needs the type of an arbitrary expression and was left out
  rather than guessed.
- **#121:** the cause was not attribute macros in most places but a namespace-opening macro directly before `namespace` (`FMT_BEGIN_NAMESPACE namespace detail`),
  which hid every definition in the file (fmt's `args.h` had none). Attribute-macro shapes written inside declaration specifiers all extract correctly in
  fixtures. C repositories were not measured against the compiler (no truth files for cJSON, autoas or lua).
- **#244:** met on leveldb (recall 0.800, method misses 88, typed-receiver precision 0.98). The gain came from one rule: when several headers define a class of one
  name, use the one the calling file includes. The Zephyr clause is checked against v0.2.14, not v0.2.11 (no 0.2.11 build to time); +9.0%.
- **#290:** on autoas, 15 edges that leaked a macro into files that never include it are gone and 44 real calls that the leak had hidden are linked.
- **Not measured:** how any of this changes an agent's behaviour. These are extractor changes judged against the compiler; no live agent benchmark was run.

## Mistakes caught on the way

- A new module-level regex named `_LOCAL` shadowed an existing one and silently broke local-variable typing; found by the existing tests.
- `#undef` was recorded with a pattern that never matched the directive text; found when the audit reproduction still failed.
- Constructor scanning ran on C code and produced 277 bogus macro edges on cJSON; restricted to C++.
- A bare call was turned into a constructor call whenever some class shared its name, which removed 31 real method edges on yaml-cpp; now only when every
  function bearing the name is a constructor.

## Later in the same session: the three clauses that were open (2026-11-22)

**#121, symbol recall on the C repositories** (compiler truth with `--std c11`, `-I .`, gcc's include directory; cJSON and Lua compile completely):

| repository | truth definitions | recall by exact name | recall by position | edge recall | edge precision |
|---|---|---|---|---|---|
| cJSON | 353 | 0.992 | 0.992 | 0.966 | 1.000 |
| Lua | 1,375 | 0.999 | 0.999 | 0.990 | 0.982 |
| autoas (63 of 301 units compile) | 405 | 0.948 | 0.990 | not scored | not scored |

autoas's exact-name figure is under 0.95 only because 16 definitions are renamed by macros (`#define crc_update crc16_update`, `#define Fls_Init Eep_Init`): the compiler names them after preprocessing, devkb has a symbol at the same lines under the source name. The other 5 misses are macro-generated (`RB_PUSH_FAST(U8, uint8_t)`), a documented limit. None of these figures changed with this batch. With the C++ numbers above, the clause holds on all six pinned repositories, with autoas measured on 21% of its translation units.

**#244, Zephyr against the real v0.2.11:** 87.0 s (v0.2.11) against 115.9 s (candidate), **+33%**, not within +10%. v0.2.14 was already +24%. The profile (cumulative, v0.2.11 to now): `cpp_graph.add_to_graph` +55.7 s (resolve +24.5, `Repo.__init__` +14.8, `scan_bodies` +16.3) and `_parse_python_file` +25.8 s (of which `_uses_in_tree` +16.0). Filed as **#405** with the attribution.

**#119, constructors:** 65% of the missed constructor edges found (268 to 93), bar 80%. The remainder is implicit construction that needs expression types (a `return` that converts, `T x = expr`, a call result as the argument): filed as **#406**.
