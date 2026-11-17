# Dogfood report: C and C++ support, on cJSON, fmt and leveldb

Written 2026-11-16. Status: exploratory. One run per agent arm, two repetitions for the leveldb question runs.

## 1. Extractor on five public repositories

`devkb/cpp_symbols.py` (standard library only), run through `build_symbols.extract` on shallow clones. The first three
are small (cJSON is 82 files), so two real embedded systems were added: **Zephyr** (RTOS, 15,912 C and C++ files) and
**autoas** (an open AUTOSAR classic automotive stack, 567 files).

| Repo | Domain | Commit | C/C++ files | Build | Symbols | Call edges |
|---|---|---|---|---|---|---|
| cJSON | C library | `6d9f244` | 99 | 0.2 s | 1,031 | 446 |
| fmt | C++ templates, headers | `57f1b59` | 75 | 0.6 s | 2,154 | 1,046 |
| leveldb | C++ classes, namespaces | `2946558` | 133 | 0.3 s | 1,545 | 1,431 |
| autoas | automotive (AUTOSAR) | `cc37096` | 567 | 3.4 s | 3,993 | 3,463 |
| Zephyr | RTOS | `7cd4b562b` | 15,912 | 44.8 s (24 s C/C++, the rest is the existing Python pass over Zephyr's scripts) | 127,521 | 173,759 |

Edge sources on the two embedded repos: autoas 1,701 unique-name, 1,476 same-file, 258 same-scope, 28 qualified;
Zephyr 99,595 unique-name, 74,160 same-file. A sample of 300 edges per repo was checked for a call site of the
callee's name in the caller's file: 300/300 on cJSON, leveldb, autoas and Zephyr, 294/300 on fmt (template calls).
This proves the name is called, not that the target is the right one of several.

Also run over libstdc++'s 143 `bits/*.h` headers: 4,919 symbols in 1.8 s.

### What dogfooding found (all fixed unless noted)

| Finding | Where seen | Fix |
|---|---|---|
| Quadratic scan of a function body: 41 s for 80 headers | libstdc++ | bounded window: 1.8 s for 143 headers |
| `namespace std _GLIBCXX_VISIBILITY(default) {` read as a function: 196 symbols instead of 4,919 | libstdc++ | namespace and class headers are tested before the function test |
| Constructor with `v_{1,2}` member initialiser lost, `operator==` lost | sample | initialiser braces skipped; operator tokens removed before the assignment test |
| A bare call linked to another class's method (`TestResult.Passed` to `TestSuite.Failed`) | fmt | a bare call from outside a class links only to free functions or its own class |
| `file_map_.end()` linked to the repo's `Slice.end` | leveldb | calls on an unseen receiver type are not linked when the name is a common standard-library method, or the receiver is a call result |
| `class Block::Iter {` recorded as `Block` | leveldb | qualified class names keep the qualifier |
| Zephyr: 66 s, and 185,420 edges of which only 4 were not "unique name in the repo": a C `static` function shared by many files got no edge | Zephyr | a bare call prefers the free function the same file defines (74,160 edges); the masking pass is one compiled regex; brace matching scans only braces (C/C++ part 30.6 s then 23 s) |
| `exit()` in an example linked to the kernel's own POSIX `exit` | autoas | a bare call to a C library name (`exit`, `memcpy`, `printf`...) is never linked across files |
| Hook and PATH: the `devkb` on PATH was PyPI 0.2.0 and built a graph of **0** symbols for leveldb | init | not an extractor fault: run from this checkout |

### Known limits (not fixed)

- A call through a pointer or reference (`builder->Add()`) is not linked to `TableBuilder.Add` unless the method name is unique in the repo. leveldb's `BuildTable`, `DoCompactionWork` and `RepairTable` are therefore missing from a pack for `WriteRawBlock`, and the pack says **Complete**.
- No C++ `RAISES` or error-signature extraction, so `pack(kind="error", subject="block checksum mismatch")` matches unrelated symbols and says **Complete**.
- `CJSON_PUBLIC(cJSON *) cJSON_Parse(...)` (a macro wrapping the return type) is not recognised by this implementation. Both agent implementations in section 3 handle it.
- Overloads share one qualified name and one node.
- No preprocessor expansion, no type inference, no template instantiation.

## 2. Does it help an agent? Questions on leveldb

Same model (Sonnet) in both arms, read-only, two tasks times two repetitions. The devkb arm had the graph and the `pack` tool; the plain arm had neither. Recall is against reference lists I wrote from the source.

| Task | Arm | Median cost | Recall (two runs) |
|---|---|---|---|
| Who reaches `TableBuilder::WriteRawBlock`, and which tests | plain | $0.137 | 1.0, 1.0 |
| | devkb | $0.098 | 1.0, 1.0 |
| What raises "block checksum mismatch", and who reaches it | plain | $0.097 | 1.0, 1.0 |
| | devkb | $0.076 | 0.82, 0.91 |

Total $0.35 with devkb against $0.47 without (26% less). In all four devkb runs the pack was wrong or incomplete (the two limits above) and the agent noticed and finished with grep, which is why cost fell but recall did not rise. Two repetitions per cell: a signal, not a result.

## 3. Does it help an agent build the feature? Exercises 4 and 5

The task: add C and C++ support to devkb itself (`bench/exercises/cpp/prompt.md`). The acceptance check
(`acceptance.py`, sha256 in `acceptance.sha256`) was fixed before any run: the repository's suite, a hand-written
fixture (symbols, kinds, lines, required and forbidden edges, test discovery), and the three repositories above.

| | Ex.4 plain | Ex.4 devkb | Ex.5 plain | Ex.5 devkb |
|---|---|---|---|---|
| Base | `88758f0` | `88758f0` | latest `origin/main`, no C++ | same |
| How devkb was given | none | `devkb init`, MCP via `.mcp.json` | none | plugin (server and skills) and `AGENTS.md` block, loading checked first |
| Cost | $1.16 | $2.44 | $1.79 | $2.01 |
| Turns / wall time | 38 / 7.5 min | 74 / 18.7 min | 44 / 11.6 min | 56 / 16.7 min |
| devkb uses | n/a | **0** | n/a | **0** (40 Bash, 8 Write, 2 Edit; the server and skills were loaded) |
| Acceptance | 29/30 | 30/30 | 30/30 | 30/30 |
| Suite at end | 276 | 297 | 294 | 294 |

Ex. 4: the plain arm's only miss was the call from a constructor to a method defined in another file.
No agent used devkb in either round (ex. 5 with the server and skills confirmed loaded), so these rows compare unaided runs, not the graph.
Costs differ by run-to-run variation as in the `adr007` rounds.

## 4. Loading findings

- With `--strict-mcp-config`, a plugin's MCP server is silently dropped (`mcp: []`) while its skills still load. The agent is told about tools it does not have. Ex. 5 avoids the flag and aborts if the server is not connected.
- `devkb init` now warns when `devkb` is only on a virtualenv's PATH (0.2.2). It fired in this setup.
- `origin/main` carries an early, unwired `devkb/cpp_symbols.py` (swept in by the plugin commit).

## 5. What would change the result

Agents do not call devkb when the prompt names the files to read. Branch `feat/pack-hook` (worktree `devkb-hook`)
adds an instruction that says which tool to use at which step, and a `PreToolUse` hook (`devkb hook pre-edit`) that
adds the file's pack to the first Edit or Write. Tested on a fixture in real Claude Code: the agent received the pack and
used it. It has not yet been run through this exercise.

Open: C++ receiver types (pointer calls), C++ error extraction, the **Complete** flag when pointer calls are not
attributed, edge precision (the acceptance check tests only that a callee's name appears in the caller's file), and a
blind review of the two implementations.
