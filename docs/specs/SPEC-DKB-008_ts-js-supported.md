---
id: SPEC-DKB-008
title: "TypeScript and JavaScript move from Partial to Supported: symbols, calls and tests an agent can trust, measured against the compiler"
type: specification
doc_type: prd
track: brownfield
status: proposed
created: 2026-11-19
updated: 2026-11-19
owner: PO
source: owner request 2026-11-19 (milestone 0.2.14, objective 2: "Update language support for js ts from partly to Supported")
supersedes: []
superseded_by: null
extends: SPEC-DKB-002
tickets: ["epic (filed with this spec)", "stories 1-8 (filed when this spec is accepted)"]
---

# SPEC-DKB-008: TypeScript and JavaScript Supported

BMAD roles:
- brief (§1);
- requirements (§2);
- architecture (§3);
- stories (§4);
- readiness (§5);
- evaluation (§6);
- results (§7, after the release that closes the stories).

Baseline: `main` at `3f56ece` (0.2.13). The pattern is SPEC-DKB-004's for C and C++, and C#'s before it.

## 1. Brief (analyst)

The README marks "TypeScript, JavaScript" 🟡 Partial: "functions, components, classes and their HTTP calls to backend
routes; not calls between them". On `main` it is less than the row says:

| What | Today (`devkb/ts_symbols.py`, 291 lines, regular expressions) |
|---|---|
| Files read | `.ts`, `.tsx` only. `.js`, `.jsx`, `.mjs` and `.cjs` are not read, so JavaScript has no symbols at all, although the read tools know the extensions. |
| Symbols | `function f`, `const f = (...) =>`, `class C`, object-literal members of API clients. No methods, no interfaces, types or enums, no `export default`, no namespaces. |
| Spans | start line only (`read_tools.START_ONLY`): no body end, so `symbol --source`, outlines and the hook's body answers cannot be exact. |
| Calls | none between functions. Only `CALLS_API` edges, from HTTP helpers to backend routes (BL-4b, ODSF-314). |
| Modules | `import` and `require` lines are recognised for the read tools' import listing. Nothing resolves a name to the file that exports it. |
| Tests | none: `describe` / `it` / `test` blocks are not test cases, so packs list no tests for TS or JS code. |
| Measurement | none. No compiler truth, no precision sample, no `bench/languages.yaml` entry. |

The language rule (2026-11-16, `bench/languages.yaml`): a language is Supported when it is checked on at least 3 real
public repositories, with a hand-checked precision sample and a CI check. C# met it with the standard library only: a
mask-and-scope scanner, with the compiler used only as truth in the benchmark (`devkb/csharp_symbols.py`). The build
depends only on `pyyaml`; this spec keeps it so.

What agents need from a TS/JS graph, in the order the 0.2.13 benchmark and SPEC-DKB-007 put them:
- a definition with its exact body;
- a file's outline;
- the callers of a function or method, across files, through imports and re-exports;
- the tests that reach it;
- an honest Incomplete when a call cannot be attributed.

## 2. Requirements (PM)

| # | Requirement |
|---|---|
| F1 | **A measurement that can be trusted.** `bench/ts/truth_tsc.mjs` uses the TypeScript compiler API, in the benchmark only and never in the build, to list each repository's symbols (with spans) and call edges. A call counts only when the checker resolves it to one declaration in the repository. JavaScript is checked with `allowJs` and `checkJs`. Vendored, generated and `node_modules` code is excluded from truth and score alike. Files the compiler cannot type are reported as "not measured". **Precision** is adjudicated: a seeded sample of at least 100 edges per repository, each wrong-by-truth edge judged by hand, with a 95% interval, committed as `docs/specs/ts-precision-sample.md`. |
| F2 | **Every TS and JS file, with real spans.** `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs` and `.cjs` are read; `.d.ts` files are read for declarations only. A mask blanks comments, strings, template literals (nested `${}`), regular-expression literals and JSX text, keeping newlines. A scope scanner then records functions, arrow and function expressions bound to a name, classes, methods, getters and setters, constructors, object-literal methods of an exported object, interfaces, type aliases, enums and namespaces, each with its start **and end** line. `export default` gets the file's default name. The language moves out of `START_ONLY`. |
| F3 | **Calls between functions, through modules.** A call resolves to a repository symbol when the name is one of the following, and every other call to a repository name is counted unresolved, so a pack says Incomplete:<br>- declared in the same scope chain;<br>- imported by ES `import` (named, default, namespace `ns.f`) or CommonJS `require` / `module.exports` / `exports.f`;<br>- re-exported (`export { f } from`, `export * from`, barrel `index` files);<br>- reached through `tsconfig` `paths` / `baseUrl`. |
| F4 | **Receivers an agent would read off the page.** A method call resolves when its receiver is one of the following. A receiver not decided by these rules stays unknown: no guess.<br>- `this` in a class, its bases (`extends`), or `super`;<br>- a variable assigned `new C(...)`;<br>- a parameter, field or variable annotated `: C`, or `C[]` element access;<br>- one level of chaining through a repository method's declared return type. |
| F5 | **Tests.** `describe` / `it` / `test` (Jest, Vitest, Mocha) and `test()` (node:test) blocks in test files are test cases. A test reaches the code it calls through F3 and F4, so packs list it. |
| F6 | **Read tools and the hook.** `symbol --source`, `outline`, `uses` and the hook's intents (SPEC-DKB-007) work on TS and JS. Definition patterns (`function X`, `const X =`, `class X`, `X(` in a class body, `export … X`) are read as locate / read-body, in each grep dialect. |
| F7 | **A CI check.** `bench/languages.yaml` gains `typescript` and `javascript` entries, each with at least 3 pinned public repositories and minimum symbols, calls and tests (about 80% of the measured value), run by `python -m devkb.bench.languages check`. |
| N1 | Adjudicated edge precision ≥ 0.95 on every scored repository, for every edge source. |
| N2 | Edge recall against the F1 truth ≥ 0.80 on every scored repository. Code the truth types only through inference (generics, overloads, `any`) is reported separately; story 1 sets that subset's target from what it measures. |
| N3 | Symbol recall ≥ 0.95, and span accuracy (end line equal to the compiler's) ≥ 0.95, on each repository's own files. |
| N4 | Build time on the largest corpus repository at most +10% against the same build with TS/JS disabled, plus no more than 2× the compiler's own parse time; measured with `bench/perf_release.py`. |
| N5 | No new node type or edge verb: `Symbol`, `CALLS` and `TESTED_BY` with new `source` values only, so no ADR. Packs stay honest: an unresolved call still makes a pack Incomplete. |

**Promotion rule.** The README row becomes ✅ Supported, for each language separately, when F1–F7 hold and N1–N3 are
met on every repository in its F7 entry, and the CI check is green on `main`. The remaining limits stay in the row in
one short clause: no general type inference, no dynamic property access, no `eval`, and decorators and framework
magic named where they are not read.

## 3. Architecture (architect)

- **Measurement (F1):** `bench/ts/truth_tsc.mjs` (Node, `typescript` from npm, pinned in `bench/ts/package.json`)
  runs only in the benchmark. It writes the same truth format as `bench/cpp/truth_clang.py`, so `quality.py`,
  `adjudicate.py` and `split_wrong.py` are reused with a language switch.
- **Extractor (F2–F5):** `devkb/ts_symbols.py` is rewritten on `csharp_symbols.py`'s two-pass design:
  1. `mask(text)` blanks comments, strings, template literals and regular-expression literals. A `/` is told apart
     from division by the previous significant token, and JSX text by the enclosing tag context.
  2. `scan_file` walks braces with a scope stack and reads each header: function, class, method, arrow binding,
     object literal, namespace.

  A module table maps each file to its exports, re-exports followed, and each import to a file, with `tsconfig`
  paths resolved once per build. The resolver attributes calls only when exactly one target fits (C#'s `_Index`
  rule), and the HTTP-route edges of BL-4b keep working (their tests stay green).
- **Read tools (F6):** `read_tools.LANG` already names the extensions. The language leaves `START_ONLY` once spans are
  real. `scripts/devkb_guardrail.py`'s definition-pattern recogniser gains the TS/JS keywords per dialect.
- **No new dependency in the build.** The TypeScript compiler is used only by the benchmark's truth, as libclang is
  for C/C++.

## 4. Stories

Each story is one ticket, filed when this specification is accepted and before the work starts. Every story keeps
`pytest` green and has fixture tests in `tests/`.

| # | Story | Done when |
|---|---|---|
| 1 | **Trustworthy TS/JS measurement** (F1) | `truth_tsc.mjs` gives symbols, spans and resolved calls on 3 TypeScript and 3 JavaScript candidate repositories. Uncompilable and vendored files are listed. The 0.2.13 baseline is recorded (symbol recall, span accuracy, edge recall, all near 0 for calls). `adjudicate.py` gives a 95% interval. The F7 repositories are chosen and pinned. |
| 2 | **Every TS/JS file, with real spans** (F2) | N3 on the F7 repositories. JavaScript files are read. Fixtures for each masked form (nested template literals, regular-expression literals, JSX) and each symbol kind. |
| 3 | **Calls through modules** (F3) | Edge recall ≥ 0.60 for imports alone, and precision ≥ 0.95. Fixtures for each import, export and `tsconfig` form, and for an ambiguous name (left unresolved and counted). |
| 4 | **Receivers and methods** (F4) | N2 (edge recall ≥ 0.80) on the F7 repositories. Fixtures for each rule, and for an undecidable receiver. |
| 5 | **Tests** (F5) | Packs list the tests that reach a function on each F7 repository. Fixtures for Jest, Vitest, Mocha and node:test shapes. |
| 6 | **Read tools and the hook on TS/JS** (F6) | `symbol --source` and `outline` are exact on the fixtures. The hook's replay (SPEC-DKB-007 §6) on recorded TS/JS searches stays under the 5% different-question floor. |
| 7 | **TypeScript and JavaScript in the CI language check** (F7) | `bench/languages.yaml` entries with ≥ 3 pinned repositories each. The check runs in the bench workflow and passes on `main`. |
| 8 | **README: TypeScript, JavaScript ✅ Supported** (promotion rule) | Only after stories 1–7 meet N1–N4: each row is promoted separately, and §7 records the final numbers. |

Order: 1 first, because every later target is measured with it. Then 2 (every later story needs real spans), 3 and 4
(the same resolver), 5 and 6, then 7 and 8.

**Candidate repositories** (story 1 measures, then chooses and pins three per language): mid-sized libraries and
applications with real tests and a `tsconfig`. TypeScript: a schema or validation library, a test runner or RPC
library, an application. JavaScript: an HTTP framework, a utility library, a CLI. Each must be under 5,000 files, MIT,
Apache or BSD licensed, and compile with `tsc` under `allowJs`.

## 5. Readiness (G0)

| Check | State |
|---|---|
| Traces to a need | owner request 2026-11-19; README row 🟡 Partial (and JavaScript files not read at all); the language rule (3 repositories, sampled precision, CI) |
| Falsifiable criteria | every story has a numeric target or a named fixture |
| Scope boundary | N5; §3 last point (no compiler in the build); general type inference, dynamic property access, `eval` out |
| Schema change governed | none needed (N5) |
| Evaluation designed before build | story 1 lands first; §1 is the baseline |
| Open risk | (1) A standard-library scanner for TS has more lexical edge cases than C# (regular-expression literals, JSX, automatic semicolon insertion); story 2's fixtures and N3 bound it. (2) Heavy use of type inference may keep N2 out of reach on some repositories; story 1 reports the inferred-only subset separately and the promotion rule names the repositories. (3) `tsconfig` variants (project references, path maps) multiply; story 3 covers `paths` and `baseUrl` and lists the rest as limits. |

## 6. Evaluation

**Correctness:** F1's truth, per story, on the F7 repositories.

**Effect on agents:** the release's tickets, run in the tri-mode benchmark with the corrected counts (#258, #263) and
the 0.2.14 harness fixes (#301–#307). The arms are no devkb, the previous release, and main. They add a TS/JS
replay of recorded searches (SPEC-DKB-007 §6). Report cost per successful run alongside cost per run.

## 7. Results

To be written after the release that closes stories 1–8.
