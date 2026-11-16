# Read tools for every language: analysis (2026-11-16)

Question: agents grep for definitions, file outlines, usages and docs. Which of that can the graph answer, for which languages, and how
reliably? Scripts: `bench/readtools/range_accuracy.py`, `bench/readtools/name_matching.py`, `bench/exercises/cpp/grep_purposes.py`.
Corpora: Python (click, httpx, lattice-scan), TypeScript (mealie), C# (MediatR, FluentValidation), C and C++ (cJSON, leveldb, fmt).
Truth for ranges: tree-sitter definitions (Python, TypeScript, C#), libclang (C, C++).

## 1. What agents search for (275 greps, 9 feature-build runs)

Cost = text returned to the model weighted by the calls still to come.

| Kind | Share of cost | The graph |
|---|---|---|
| Filter another command's output | 30.1% | not a search |
| Where is X defined (90% read the body with -A/-B/-C) | 14.7% | data exists (Symbol, line_start, line_end) |
| Outline of a file | 11.9% | data exists |
| Callers or users of a known function | 11.7% | `callers`, `pack` |
| Text in docs, specs, tickets | 9.6% | partly (`find_docs`) |
| Module, import, key or name with no node | 7.9% | no node |
| String or pattern in code | 6.1% | partly |
| Tests | 3.5% | `tests_for` |
| Constant or macro | 3.3% | no node |
| External repository or scratch file | 0.9% | outside the graph |
| Count or check | 0.1% | not a search |

Definition + outline = 27% of all grep cost (38% of real searches). Six kinds reach 80%.

## 2. How accurate are the stored names and ranges? (per language, against an independent parse)

| Language | Repository | Symbols | Truth defs | Recall | Precision | End line exact | Start line |
|---|---|---|---|---|---|---|---|
| Python | click | 2,044 | 2,094 | 0.98 | 1.00 | 99.9% | name row 100% |
| Python | httpx | 1,229 | 1,241 | 0.99 | 1.00 | 100% | 100% |
| Python | lattice-scan | 1,733 | 1,733 | 1.00 | 1.00 | 100% | 100% |
| C# | MediatR | 1,560 | 1,639 | 0.85 | 0.90 | 99.9% | name row 81%, node start 19% |
| C# | FluentValidation | 2,180 | 2,428 | 0.83 | 0.92 | 100% | name row 56%, node start 44% |
| C | cJSON | 1,070 | 967 | 0.99 | 0.89 | 99.8% | 100% |
| C++ | leveldb | 1,586 | 1,484 | 0.91 | 0.91 | 92.8% | name row 92% |
| **TypeScript** | mealie | 631 | 1,090 | **0.58** | 1.00 | **12.9%** | within 1 line |

Findings:
1. **Python, C#, C and C++ store exact end lines** (93 to 100%), so a symbol's source can be returned bounded by the graph's own range.
2. **TypeScript, JavaScript (and Odoo XML) store `line_end` = `line_start` for every symbol** (632 of 632 in mealie). The extractor computes the body end internally (`_find_symbols` returns `body_end`) and `build_symbols.py` writes `line_start` as the end. Recall is 0.58 because class methods and nested declarations are not found.
3. **C# misses 12.5% of methods and 29% of constructors** (generic and extension methods among them) and has no `interface` Symbols; the graph does hold properties.
4. `line_start` is the **name row** for Python and C/C++ symbols, and the declaration start (modifiers or attributes) for some C# ones: the tool must show the signature line itself, not assume.
5. **Overloads share one node** (C#, C++): one name resolves to one range, which is the last definition.

## 3. How long are the bodies a `symbol` call would return?

Function and method bodies, lines: Python median 9, p90 32 to 40; C# median 3 to 4, p90 11 to 24; leveldb median 5, p90 28; cJSON median 11, p90 81; fmt median 5, p90 27 (max 3,588).
Up to 80 lines covers 97 to 99% of Python, 99% of C#, 96 to 98% of leveldb and fmt, and 89% of cJSON. A fixed `grep -A25` over-reads 87% of Python functions and cuts 11% short.

## 4. Which name-matching tiers earn their place? (real names, one typo, two words, lower case, prefix; 200 non-existent names)

Success at rank 1 / 3 / 8 (click, mealie, FluentValidation, leveldb pooled by eye):

| Query | A exact | B + prefix/substring | C + word overlap | D + edit similarity |
|---|---|---|---|---|
| exact name | 100 | 100 | 100 | 100 |
| wrong case | 98 to 100 | same | same | same |
| one typo | 0 to 1 | 0 to 5 | 18 to 36 at rank 1 | **96 to 99** at rank 1 |
| two words of the name | 6 to 37 | same | **47 to 92** at rank 1, 66 to 98 at rank 3 | 44 to 89 |
| first half of the name | 0 | 58 to 80 at rank 1, 81 to 96 at rank 3 | same | same |

**False accepts** (a name that does not exist gets a match): word overlap with a threshold of 40 accepts **35 to 50%**; edit similarity needs a score of at least 55 to fall to **1 to 7%**.
Shared short names: 10 to 26% of names map to several symbols (leveldb 26%), so ties need a ranking rule.

Design consequences: exact and case-insensitive first; then qualified, glob and regex; then prefix, substring and words; edit similarity only as a fallback and labelled as a guess below 55.

## 5. Capability matrix the tools must respect

| Capability | Python | C# | C, C++ | TypeScript, JavaScript |
|---|---|---|---|---|
| Exact end line (source can be bounded) | yes | yes | yes (93 to 100%) | **no** |
| Complete definition coverage | 98 to 100% | 83 to 85% | 91 to 99% | 58% |
| Qualified name separator | `.` | `.` | `.` (C++), none (C) | none (`container.entry` for object literals) |
| Overloads share a node | no | yes | yes | no |
| `language` property on the node | no | no | not on main (only on the unmerged SPEC-DKB-002 branch) | no |
