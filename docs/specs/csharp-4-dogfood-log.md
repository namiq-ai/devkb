# Dogfood log: devkb used on its own code during C# round 4 (#40)

Every navigation question asked while building round 4 went to devkb first (`devkb outline | symbol --source | uses |
pack`, graph of this repository built by the code under change), and the answer was checked against the source. Where
devkb was wrong, incomplete or noisy, the limitation is recorded here with its cause, and fixed in this round when it
is in reach.

Graph: `devkb build --project .` on `main` at `4ef4766` (2,750 nodes, 7,326 edges, 8 s).

| # | Question | devkb's answer | Checked against | Verdict | Limitation, cause | Resolved |
|---|---|---|---|---|---|---|
| Q1 | Layout of `devkb/csharp_symbols.py` | `outline`: 72 symbols with line ranges and docstrings | the file | right, one call instead of reading 1,565 lines | | |
| Q2 | Who calls `_Index.compatible`? | `pack refactor`: 1 file, line 906, Complete | grep: lines 906, 908 | right | | |
| D1 | Who calls `_Index.extension`? | `pack refactor`: **0 callers** | grep: 3 sites (`index.extension(...)` at 1344, 1377, 1379) | **wrong** | Python typed receivers: `index: _Index` is an annotated parameter, but `_class_ref` only treats capitalised names as classes, so `_Index` (a private class) never types anything | yes: `_looks_like_class` accepts leading underscores; after: 1 caller file, line 1344, **Complete**; devkb's self-graph gained 117 typed edges |
| D2 | (same pack) coverage line | "Incomplete: 1 call site(s) could not be attributed" | 3 sites unattributed | **wrong count** | the unresolved set is keyed by (file, caller, name): three calls from one caller count once, but the text says "call site(s)" | yes: "calls under this name from N function(s) could not be attributed" |
| D3 | Who calls `_Index.member`? | `pack refactor`: caller line `csharp_symbols.py:965: def member(...)` | the recursive call is at 981 | **wrong evidence** | `Packer.call_site` scans the caller's lines from `line_start`; for a recursive method the first line matching `member(` is its own `def` | yes: `call_site` skips a `def name(` line; after: line 981 |
| D4 | `uses extension` | 31 of 77 hits shown, mostly lines of benchmark transcripts (`bench/exercises/**/*.jsonl`) | | **noisy** | `uses` searches every tracked file, data included; the budget went to JSON transcripts | yes: `.jsonl`, `.ndjson`, `.tsv`, `.log` join `NOT_CODE` (back with `--docs`) |
| Q3 | Body of `_typed_calls`, `_annotation_class`, `_class_ref` | `symbol --source` | the file | right; `symbol` without `--source` prints only the header (by design, said in `--help`) | | |
| D5 | `docs "registry pack check"` | 11 documents, each matching one of the words | | **noisy** | `docs` ranks by any word; a phrase is not kept together | not in this round (noted) |

Regression tests for D1–D4: `tests/test_dogfood_round4.py` (each fails on `4ef4766`). The Python change (D1) alters
Python graphs; CI's registry `prepare` jobs (`bench/truth_check.py` on the seven Python repositories) gate it.
