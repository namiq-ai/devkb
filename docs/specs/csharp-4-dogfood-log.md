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
| Q4 | Where `_calls_in` reads a chained receiver | `uses "re:chained = (None\|True\|False)" --under devkb` | the file | right (lines 1309, 1317, 1321); `symbol _calls_in` warned the graph was one commit stale, which was true | | |
| D6 | (same `uses`) | "showing 3 of 4 hits … Narrow with under=PATH" though `under` was given | 4 hits, one file | **misleading hint** | the per-file cap (3) hid the fourth hit; the hint names `under` even when it is set | not in this round (noted) |
| Q5 | Body of `_calls_in` (330 lines) | `symbol --source` prints at most 200 lines (by design) | | partly: the rest was read with the editor | | |
| Q6 | Callers of the new `_subst`, `better` (after implementing F1/F2) | `pack refactor`: lines 1217 and 1159 (+ more), Complete | grep | right | | |
| D7 | Callers of the new `binding_for`, `field_bound` | `pack refactor`: **none**, "Incomplete … search `csharp_symbols.py`" | grep: one call each, at 1653 and 1476 | **missed** (honestly marked incomplete) | both are called through `index` from functions nested inside `_calls_in`; the Python extractor typed a nested function's own parameters only, not the names it closes over | yes: nested functions inherit the enclosing function's typed names (own parameters shadow); after: both Complete with their lines |
| D8 | (value report on 0.2.7, EF Core) `callers CommandBatchPreparer.BatchCommands` | error: "2 symbols named …; pass one as path::name" | the second is `eng/harness-evaluation/skills/update-pipeline/fixtures/...`, a fixture copy of the real class | **ambiguous for no reason** | fixture copies of production code under `eng/**/fixtures/` are indexed as code, so a name the repository defines once has two symbols | not in this round (noted for the extractors: treat `**/fixtures/**` copies as test data) |
| D9 | (value report on 0.2.7, EF Core) a chain question with the read tools in `lean-pack` | the devkb agent made 7 `uses` and 5 `outline` calls after the first pack and listed 33–39 methods; scored 0.25 against 9 callers | compiler truth, then the source | **right, the benchmark was wrong** | the truth tool recorded calls only; the target is reached through four properties (`bench/exercises/csharp/truth-corrections.md`). On the regenerated truth those runs score 0.93 | truth tool fixed (property and indexer accesses are edges; ids qualified by assembly), truth regenerated |

Regression tests for D1–D4 and D7: `tests/test_dogfood_round4.py` (each fails on `4ef4766`). The Python change (D1) alters
Python graphs; CI's registry `prepare` jobs (`bench/truth_check.py` on the seven Python repositories) gate it.
