---
id: ADR-DEVKB-010
title: "ADR-DEVKB-010: Read tools for every language: symbol, outline, uses, search_docs"
type: adr
status: accepted
created: 2026-11-16
updated: 2026-11-16
owner: TL
supersedes: []
superseded_by: null
implements: SPEC-DKB-003
amends: []
tickets: ["initiative-read-tools-for-every-language 1.1-1.12, 2.1-2.7", "backlog 3", "backlog 4", "backlog 5"]
---

# ADR-DEVKB-010: Read tools for every language: symbol, outline, uses, search_docs

**Status**: Accepted by the owner's delegate on 2026-11-16, with the amendments in section 10. D1 to D7 are the factory owner's decisions of 2026-11-16, recorded as given. Items tagged `[ASSUMPTION]` were chosen by the PO in a non-interactive run and are not the owner's. Move to Accepted (owner and TL) before story 1.1 merges. This ADR changes no node type, edge verb or Symbol property, so `ADR-SDP-DEVKB-001` does not gate it; it does change the public tool list, which is why it is recorded.

**Evidence.** `docs/analysis/read-tools-analysis.md` (275 greps in nine feature builds; accuracy of stored names and ranges on eight repositories in five languages; a name-matching experiment with false-accept rates). Figures below are quoted from it.

## Decisions

| Id | Decision |
|---|---|
| D1 | Four new read tools, `symbol(query)`, `outline(path)`, `uses(name)`, `search_docs(query)`, all in `lean-pack`, `dev` and `all`, each with a shell equivalent (`devkb symbol\|outline\|uses\|docs`). Replies are compact text, not JSON, and end with the staleness note when the graph is stale. |
| D2 | `symbol` resolves a name like grep, in tiers, stopping at the first tier with hits. A fuzzy result is labelled `similar` with its score; below 55 the answer is "no symbol named X" with suggestions. Ties are ranked. Filters `kind`, `under`, `limit`. |
| D3 | `symbol(..., source=True)` returns the source lines bounded by the graph's own `line_start` and `line_end` (default 80 lines, hard cap 200). It never states an end line it does not have: where `line_end == line_start` it says `end unknown` and shows a 40-line window marked approximate. It says `moved` when the signature line no longer holds the name. |
| D4 | `outline(path)` returns a file's symbols in source order with nesting, plus its import or include lines; a directory returns files with symbol counts. |
| D5 | `uses(name)` is a graph-annotated text search, labelled as text matches, never Complete. |
| D6 | `search_docs(query)` searches tracked documentation files and returns passages with their nearest heading, specs and ADRs first. |
| D7 | Success is measured after the build: definition and outline greps fall at least 60% with no loss in acceptance score, and per-language end-line floors hold (Python and C# 99%, C and C++ 92%, TypeScript 95% after its prerequisite ticket). |

## 1. Language-agnostic rule

Nothing in a tool's logic is written per language. Every language difference is a row of one **capability table** keyed by file extension, read through one function `capability(path)`. A new language adds a row and a fixture, not a branch. `[ASSUMPTION]` A path with no row is `range=start-only`, separator `.`, `overloads=separate`: the safe side of every flag.

| Extension | Language | `range` | Qualified separator stored | `overloads` | Start line is |
|---|---|---|---|---|---|
| `.py` | Python | exact | `.` | separate | name row |
| `.cs` | C# | exact | `.` | shared | name row or node start (attributes, modifiers) |
| `.c` | C | exact | none | separate | name row |
| `.h` | C or C++ (not told apart on main) | exact | `.` or none | shared | name row |
| `.cc .cpp .cxx .hh .hpp .hxx` | C++ | exact | `.` (source `::`) | shared | name row |
| `.ts .tsx .js .jsx .mjs .cjs` | TypeScript, JavaScript | **start-only** until backlog 3, then exact | none; `container.entry` for object literals | separate | within 1 line of the name |
| `.xml` (Odoo declarations) | Odoo XML | **start-only** | none | separate | declaration row |

`range=exact` means the stored `line_end` is the definition's last line within the accuracy of section 5; `start-only` means `line_end == line_start` and carries no information. When the `language` property and a stored `range` flag exist (backlog 5), `capability(path)` reads them first and the table is the fallback; no tool changes.

## 2. Reply conventions (all four tools)

- **Text**, one record per block, no JSON, no markdown tables. Paths are repository-relative. Line numbers are 1-based. A line range is `L40-71`; a start-only symbol is `L40 (end unknown)`.
- **First line** names the tool, the query as understood and the count: `symbol "load_config": 2 matches (exact)`.
- **Last line**, only when the graph is stale: `graph stale: built at <head8>, repository is <n> commits ahead; ranges and names may have moved, re-read what you edit.` Same test as `_meta.stale` (`Staleness.check`).
- **Omissions are counted**: every cap ends with `(N more ...)` saying what it cut and how to see it.
- **Errors** are one line: `no graph yet: ...` (as `_LazyAPI.call`), `bad regular expression: <reason>`, `path outside the repository`. A tool never falls back silently to another mode.
- **Byte budget** `[ASSUMPTION]`: 6,000 bytes per reply, enforced by cutting whole records from the end and saying so. `_fit` (JSON lists) does not apply; the text builder owns this.

## 3. `symbol(query, kind="", under="", limit=8, source=False, lines=80)`

### 3.1 Tier order (D2)

A query is lower-cased for comparison only. Tiers run in this order; the first with at least one hit decides the answer. `how` is the value printed.

| # | Tier | `how` | Rule |
|---|---|---|---|
| 1 | exact | `exact` | case-insensitive equality with the short name (the last segment of the stored qualified name; `CompactIndex.short`) |
| 2 | qualified | `qualified` | `.`, `::` and `#` are one separator. The query's segments equal the trailing segments of a stored qualified name, case-insensitive, **and** that is the whole name; `path::name` or `path/file.py::name` restricts to files whose path ends with `path` |
| 3 | suffix | `suffix` | the query's segments equal a trailing run of segments of the qualified name (`Store.get` finds `kv.Store.get`) |
| 4 | glob | `glob` | the query holds `*` or `?`; matched on the short name, or on the qualified name when it holds a separator |
| 5 | regex | `regex` | a `re:` prefix, or auto-detected `[ASSUMPTION]` when the query holds one of `^ $ + ( ) [ ] { } \|` or a backslash; matched with `re.search` on the short name, case-insensitive; an invalid expression is an error, not a fallback |
| 6 | prefix, then substring | `prefix`, `substring` | prefix of the short name; if none, substring of at least 3 characters. `[ASSUMPTION]` prefix and substring are separate steps in that order |
| 7 | fuzzy | `similar NN` | see 3.2 |

### 3.2 Fuzzy tier and the threshold (D2)

The experiment (200 non-existent names) found word overlap alone accepts a missing name 35 to 50% of the time, and edit similarity with a threshold of 55 only 1 to 7%. Therefore:

- **Candidates** come from word overlap (snake_case and camelCase split, stemmed as `service.words`) and from edit similarity; both may propose.
- **Score** is the edit similarity of the lower-cased short names, 0 to 100. `[ASSUMPTION]` The scale is the one `bench/readtools/name_matching.py` measures; the story that builds it pins the function to that script's numbers.
- **Accept** only a candidate with score ≥ 55, printed `how similar 78`. `[ASSUMPTION]` Word overlap proposes and orders; it never accepts on its own, because that is the 35 to 50% case.
- **Below 55**, or when only word-overlap candidates exist: the reply is `no symbol named "X"` and, under `closest names (not matches):`, up to 5 names with path and score. The reply does not return source for them.
- A similar match is never reached when any earlier tier had a hit.

### 3.3 Match record

```
1. src/app/config.py  function  L40-71  def load_config(path: str) -> Config:
   "Load the YAML config and apply defaults."   callers 7   how exact
```

| Field | Source | Rule |
|---|---|---|
| file, kind | Symbol key (`path::qualified`), `kind` | as stored |
| range | `line_start`, `line_end`, `capability(path).range` | `L<s>-<e>` when exact; `L<s> (end unknown)` when start-only |
| signature | the file text | first line at or after `line_start` (up to 5 lines on) that contains the short name, trimmed to 160 characters; none found: `moved` and no signature |
| docstring | `docstring_summary`, else absent | first line only, trimmed to 120 characters |
| callers | `CompactIndex.inn["CALLS"]` | number of direct callers, one hop `[ASSUMPTION]`; a number, not a coverage claim |
| how | tier | see 3.1; plus `moved`, `shared range (N overloads)` where they hold |

### 3.4 Ranking of ties (D2)

Symbols sharing a short name (10 to 26% of names) are ordered by this key, each step breaking the tie of the one before:

1. production before test code (`is_test_path`);
2. shallower qualified name first (fewer segments);
3. more callers first;
4. path, ascending.

In tier 7 the score is sorted first, then this key. `limit` cuts after ranking and the reply says `(N more matches)`. Filters apply **before** tiering so that `kind="class"` changes what is found, not only what is shown: `kind` equals a stored `kind` value (an unknown value lists the kinds present); `under` is a path prefix.

### 3.5 Source (D3)

`source=True` adds, to the **first** match only, a block of source lines read from the working tree, each prefixed with its line number. `lines` is the maximum, default 80, hard cap 200 (a larger value is cut to 200 and the reply says so).

| Case | Reply |
|---|---|
| `range=exact`, range ≤ `lines` | the whole range |
| `range=exact`, range > `lines` | the first `lines` lines, then `(N more lines; L<s>-<e>)` |
| class-like (the symbol has nested symbols in the same file) and range > `lines` | the outline of the symbol (its nested symbols, as `outline` prints them) instead of its body; `[ASSUMPTION]` when the range fits, the body is returned |
| `range=start-only` | `end unknown`; a window of at most 40 lines from the start, marked `approximate window, not the symbol's range`; a class-like symbol returns its outline by nesting |
| signature line does not contain the name | `moved: "<name>" is not at L<s>; the file changed after the graph was built`; no source is returned; the reply names `uses` `[ASSUMPTION]` |

The tool never prints an end line that is not stored. It never extends a range to a closing brace it found by reading (that would be a second extractor).

## 4. `outline(path)` (D4)

- Resolution: an exact tracked path; else a unique path suffix (`model.py`); several suffix matches: the reply lists up to 8 and asks for a longer one; none: `no file named ...`.
- **File**: header `path  <language> <n> symbols  range=<exact|start-only>`; then the import or include lines at the top of the file (`import`, `from`, `#include`, `using`, `require(`, `use`; at most 30, only before the first symbol), then one line per symbol in source order, indented by nesting:

```
  class Config  L12-58  "Settings read from YAML."
    method get  L20-31  "Return a key."
```

  Nesting comes from the qualified name (parent = the stored name with its last segment removed, when that parent is a Symbol in the file); `[ASSUMPTION]` it does not come from line containment, so it holds for start-only languages. A start-only symbol prints `L40` with no end. Source order is `line_start`. At most 150 symbol lines (`(N more symbols)`).
- **No indexed symbols**: `no indexed symbols in <path>` followed by `indexed languages: Python, TypeScript, JavaScript, C#, C, C++, Odoo XML` (from the capability table), and a line count; the imports are still shown when the file is a source file.
- **Directory**: its tracked files, one per line, `path  <n> symbols`, files with no symbols last, at most 60 (`(N more files)`); subdirectories collapse to `dir/  <n> files  <n> symbols`.

## 5. `uses(name, under="")` (D5)

First line is always `uses "X": text matches, not resolved references; tracked files only, not complete`.

- **Mode**: an identifier (`^[A-Za-z_][A-Za-z0-9_]*$`) is a **whole-word** search, case-sensitive; a query with a regex character (3.1 tier 5) is a **regular expression**; anything else is **fixed text**. The mode is printed (`mode word`).
- **Files searched**: the repository's tracked files `[ASSUMPTION]` (`git ls-files`; a non-git checkout walks the tree), text only (a NUL byte in the first 4 KB skips the file), larger than 1 MB skipped, `is_generated_path` paths skipped. The count of files skipped for these reasons is printed. This is what lets `uses` find modules, constants, macros, config keys and Kconfig-style names that are not graph nodes (11% of grep cost).
- **Definitions first**: symbols that tiers 1 to 3 of `symbol` give for the name, one line each (`defined: path L40-71 function`), at most 5.
- **Hits**: `path:line  in <qualified name> | after <qualified name> | top level  <line, trimmed to 160>`.
  - `in` is used only when `range=exact` and the line is inside `[line_start, line_end]` of the innermost such Symbol.
  - `after` is used for a start-only file: the nearest Symbol that starts above the line. It is a guess about position and the word says so.
  - `top level` is a line in no Symbol range.
  - Hits are grouped by file, then by enclosing symbol; production files before test files (`is_test_path`), then by hit count descending, then path.
- **Caps** (defaults, as D5): 12 files, 36 hits, 3 hits per file. The reply ends `showing 9 of 31 hits in 7 of 18 files; omitted: 22 hits (13 in tests), 11 files. Narrow with under=PATH.`
- A Symbol is not a use: the definition line of the name is shown under `defined`, not repeated as a hit.

## 6. `search_docs(query, under="")` (D6)

- **Files**: tracked `.md .rst .txt .adoc` files, excluding generated paths. Query terms are split on whitespace and lower-cased; a double-quoted phrase is one term.
- **Rank** `[ASSUMPTION]`: (1) files under `docs/spec`, `docs/adr`, or named `SPEC-*` or `ADR-*` first; (2) within a group, files containing more distinct terms; (3) more matching lines; (4) path.
- **Record**: `path  <n> matching lines`, then per hit `L<line>  under "<nearest preceding heading>"  <line text, trimmed to 160>`; the heading is the nearest preceding Markdown `#` heading, an AsciiDoc `=` heading, or an RST title (a line followed by an `===`, `---` or `~~~` underline); none: `top of file`.
- **Caps** as `uses`: 12 files, 36 hits, 3 per file, totals and omissions printed. A line matches when it holds at least one term; lines holding the most distinct terms are shown first.
- `find_docs` (ranked specs, ADRs, design docs by topic, from the graph) is unchanged and stays in its toolsets.

## 7. Toolsets, shell and wiring (D1)

| Where | Change |
|---|---|
| `mcp_server.py` `TOOLSETS` | `lean-pack`, `dev` and `all` gain the four tools; `core`, `workflow`, `docs` and `lean` do not (`lean` stays as measured) |
| `process_api.py` | four methods return a text reply; `call` handles a text reply without `_fit`; `_meta` is replaced by the staleness line; `TOOL_ARGS` gains `symbol`, `outline`, `uses`, `docs` and `TEXT_TOOLS` lists them |
| `symbol` collision | the old `symbol(name, limit)` JSON method and `devkb symbol NAME` are replaced; tier 1 returns what it returned (`[ASSUMPTION]`, A1) |
| instructions | `INSTRUCTIONS` in `mcp_server.py`, `AGENTS_BLOCK` in `init.py`, `skills/devkb-lean-pack/SKILL.md` and its `plugins/devkb` copy, `README.md` say when to use each tool instead of grep |

## 8. What each language can promise

The promise is a property of the capability table and of the measured accuracy, not of the tool's wording. **Accuracy** columns are from the analysis (truth: tree-sitter for Python, TypeScript, C#; libclang for C and C++).

| | Python | C# | C | C++ | TypeScript, JavaScript | Odoo XML |
|---|---|---|---|---|---|---|
| Definition recall (symbols found / definitions) | 98 to 100% | 83 to 85% | 99% | 91% | **58%** | not measured |
| Stored end line exact | 99.9 to 100% | 99.9 to 100% | 99.8% | 92.8% | **12.9%** (all `line_end = line_start`) | none stored |
| `symbol` says | a miss is reliable evidence: "no symbol named X" | a miss is **not** proof: constructors (29% missing), generic and extension methods (12.5% of methods) and `interface` are not Symbols | a miss for a macro or constant says it is not a graph node and names `uses` | as C#, for overloads sharing a node | a miss says class methods and nested declarations are often not indexed | a miss says declarations only |
| Source returned | exact range | exact range; signature found by scanning from `line_start` | exact range | exact range (7% of ends may differ from the compiler's) | `end unknown`, 40-line window | `end unknown`, 40-line window |
| Overloads | n/a | one node: the last definition's range; reply says `shared range` | n/a (static duplicates are separate nodes by file) | as C# | n/a | n/a |
| Qualified query | `Class.method`, `pkg.mod.func` | `Namespace.Class.Method` | name only; `path::name` | `ns::Class::method` read as `.` | `container.entry`; class members only when indexed | declaration id |
| `outline` | exact nesting | exact nesting; interfaces and constructors absent | flat (functions, structs) | nesting by class | flat, starts only | flat |
| `uses` enclosing symbol | `in` | `in` | `in` | `in` | `after` (start-only) | `after` |

Floors after the build (D7, measured by `bench/readtools/range_accuracy.py REPO GRAPH LANG`): end line exact ≥ 99% Python and C#, ≥ 92% C and C++, ≥ 95% TypeScript (**after backlog 3**; until then the TypeScript floor is not claimed and `range=start-only` holds).

## 9. Fixtures (acceptance is tied to these names)

All under `tests/fixtures/readtools/`, built with `devkb build --project <dir>`, each with an `expected.json` of hand-written answers (name, kind, start, end, callers) that no extractor produced.

| Name | Directory | Holds |
|---|---|---|
| FX-PY | `py/` | `app/config.py` (class `Config` with `get`, `reload`; function `load_config` with a docstring and 3 direct callers; constant `DEFAULT_PATH`; imports `yaml` and `os`), `app/cache.py` (class `Cache` with `get`), `app/util.py` (calls `load_config`; `load_config_text`), `tests/test_config.py` (a test helper `get`, calls `load_config`) |
| FX-TS | `ts/` | `src/config.ts` (function `loadConfig`, arrow `parseKey`, class `Store` with `get`, `set`), `src/routes.js` (object literal `routes` with `list`, `show`), `src/config.test.ts` |
| FX-CS | `cs/` | `src/Loader.cs` (class `Loader`: constructor, `Load(string)`, `Load(Stream)`, generic `Load<T>`, a property; `interface ILoader`), `tests/LoaderTests.cs` with an attribute above a test method |
| FX-C | `c/` | `src/json.c`, `src/json.h` (`json_parse` of 150 lines, `static skip_ws` in `json.c` and in `test_json.c`, macro `JSON_MAX_DEPTH`, `const int MAX_NODES`), `test/test_json.c` |
| FX-CPP | `cpp/` | `src/store.hpp`, `src/store.cpp` (namespace `kv`, class `Store` with overloaded `put(int)` and `put(std::string)` and a template `get`; a free `get`; `kv::get`; a declaration in the header and its definition in the `.cpp`), `test/store_test.cpp` |
| FX-MIX | `mixed/` | `bind/lib.c` (`add_one`), `bind/wrap.py` (a Python `add_one` calling it through `ctypes`), `ui/app.ts` (a start-only `add_one`), an Odoo view declaration under `ui/`, `docs/spec/SPEC-X.md`, `docs/adr/ADR-1.md`, `docs/notes.rst`, `Makefile`, `app.cfg` holding the key `retry_limit` |

Fixtures are synthetic (no customer data; RFC5737 addresses if one is needed).

## 10. Consequences

- **Good.** One call replaces a grep and the reads it triggers (definition and outline are 27% of grep cost; bodies are 97 to 99% under 80 lines for Python and C#). Honest labels (`similar`, `end unknown`, `after`, `moved`, text matches) keep an agent from trusting what the graph cannot back.
- **Cost.** Four tools add to the tool list the model loads each turn; D7 measures whether they pay for themselves. `uses` and `search_docs` read the working tree at call time, so their speed is a file scan: `[ASSUMPTION]` target under 1 s on a 5,000-file repository, measured in story 1.11, not guaranteed.
- **Risk.** The `symbol` replacement changes a reply shape that two existing tests read (A1). Word overlap proposing and never accepting is the PO's reading of D2; the owner may overrule (open question 1).
- **Not decided here.** Resolving references (callers by name text) beyond one hop; a regular expression over the graph other than on names; replacing `find_code`.

## Open questions

1. D2 lists word overlap before edit similarity and also says word overlap alone accepts a missing name 35 to 50% of the time. This ADR lets word overlap propose and edit similarity (≥ 55) accept. Pick: keep, and measure in story 1.4 against `bench/readtools/name_matching.py`. The owner may instead give word overlap its own score floor.
2. Should `symbol` return source for more than the first match? Pick: no; the agent narrows, one body per call.
3. TypeScript class-method recall (0.58) is not a ticket; it is a note in backlog 3. Pick: leave it so.

## 10. Amendments made while building (2026-11-16), with the measurement behind each

| # | The draft said | What was built | Why |
|---|---|---|---|
| A1 | Word overlap only proposes names; only edit similarity at 55 or more accepts. | A `words` tier **accepts** when every word of the query is a word of the name (snake_case and camelCase split), labelled `words`. | The experiment's 35 to 50% false accepts were for a loose overlap score with a threshold of 40. The strict form (all query words present) accepted a non-existent name in 3% (mealie) and 4% (leveldb) of 300 queries, and it is what makes "parse json" find `parse_json_string` (47 to 92% at rank 1). Edit similarity stays a fallback with the floor of 55. |
| A2 | A symbol whose signature is not at `line_start` returns `moved` and no source. | The tool looks within 150 lines for the name on a definition-like line; found: the range is shifted by that distance, flagged `adjusted`, and the source is returned; not found: `moved` and no source. | During an edit session the graph is stale for every symbol below the edit; returning nothing there would send the agent back to grep exactly when it needs the tool. The shift is shown, never silent. |
| A3 | Each tool returns a text reply. | `ProcessAPI` methods return a dict (tested, and `_meta` is kept); `read_tools.render_*` turns it into the text of section 2; the MCP server and the shell print the text. | Structured replies are testable and reusable; the agent still sees only the text. `call` skips `_fit` for these four tools (`_OWN_CAPS`). |
| A4 | `uses` reports skipped files (binary, over 1 MB, generated). | `git grep -I` skips binary files; the size and generated-path skips are not reported. | Not built in this pass. |
| A5 | `outline` of a directory collapses subdirectories and lists files without symbols last. | It lists files that have symbols, by symbol count, at most 40. | Not built in this pass. |
| A6 | `search_docs` honours a double-quoted phrase. | Terms are split on whitespace. | Not built in this pass. |
