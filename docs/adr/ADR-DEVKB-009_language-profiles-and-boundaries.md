---
id: ADR-DEVKB-009
title: "ADR-DEVKB-009: Language profiles and cross-language boundaries"
type: adr
status: accepted
created: 2026-11-16
updated: 2026-11-16
owner: TL
supersedes: []
superseded_by: null
implements: SPEC-DKB-002
amends: ADR-DKB-001
tickets: []
---

# ADR-DEVKB-009: Language profiles and cross-language boundaries

**Status**: Accepted (owner's delegate, 2026-11-16). D7 and D8 are the factory owner's decisions of 2026-11-16, recorded as given; items tagged `[ASSUMPTION]` were inferred by the PO in a non-interactive run and are not the owner's. `devkb/ontology.md` changes under this ADR, and `ADR-SDP-DEVKB-001` allows that only through an Accepted ADR: this ADR must be Accepted before the first story of SPEC-DKB-002 merges.

**Numbering.** The code branch `feat/cpp-support` cites the C/C++ ADR as `ADR-DEVKB-008`; this repository files it as `ADR-DKB-001`. They are one record. This ADR is numbered 009 as asked and amends it; D1 to D6 are unchanged and D7, D8 continue the series.

## Decisions

| Id | Decision |
|---|---|
| D7 | C and C++ are separate rule profiles over one scanner. `language` (`c` or `cpp`) is recorded on every C/C++ File and Symbol. A `.h` file's language is decided by what includes it and what it contains; default `c`. The C profile resolves through linkage; the C++ profile keeps classes, receivers and overloads. Each profile reports its own Complete or Incomplete. The compiler matters for verification flags and tolerated dialect keywords, not for the scanner. |
| D8 | One graph, per-language extraction, global resolution across languages. A `CALLS` edge may cross languages; its `source` names the mechanism. Extractors emit boundary records; one resolver matches them. Exported symbols carry `abi_exported` and `boundary_kind`, and their pack is Complete for the languages read with a note. Order: C++ and C through `extern "C"`, then Python and C, then Kconfig and devicetree as `ConfigKey`. JNI is deferred. |

## 1. Evidence

| Corpus | C | C++ | Headers | Reads |
|---|---|---|---|---|
| Zephyr | 10,044 `.c` | 70 files | 5,802 `.h`: 2 with C++ constructs, 1,640 with an `extern "C"` guard | 56% of C files read `CONFIG_*` |
| autoas | 210 `.c` | 132 files | 94 of 225 headers guarded | 279 C++-to-C and 61 C-to-C++ edges already link |

## 2. Data contract (D7)

| Property | On | Value |
|---|---|---|
| `language` | File, Symbol (C/C++ only) | `c` or `cpp`. A Symbol takes its File's language. Python and TypeScript nodes get none. |
| `linkage` | Symbol | `internal` (`static`, anonymous namespace), `c` (C definition without `static`, or inside `extern "C"`), `cpp` (otherwise) |
| `consumed_by_cpp` | File | true for a C header with an `extern "C"` guard |

**`.h` language, in this order** `[ASSUMPTION]`: (1) a C++ construct (`namespace`, `template`, `class` or `struct` with an access label `public:` `private:` `protected:`) in masked text outside any `#ifdef __cplusplus` region gives `cpp`; (2) otherwise an `extern "C"` guard gives `c` and `consumed_by_cpp`; (3) otherwise, one or more includers all C++ gives `cpp`; (4) otherwise `c`. One include hop. A lone `::` no longer decides: this replaces the `::` test of ADR-DKB-001 §2 and is the one place D7 changes D1 to D6. Extensions other than `.h` follow ADR-DKB-001 §2: `.c` is `c`; `.cc .cpp .cxx .hh .hpp .hxx` are `cpp`.

**C profile.** A call resolves: `static` function in the caller's own file; non-static function when exactly one non-static definition of the name exists in the repository (denylist applies); else unresolved. No class, receiver, qualified or overload rule applies. A function-pointer table entry, an ops-struct field initializer and any other use of a function's name without `(` is an unresolved indirect reference with reason `indirect-reference`.

**C++ profile.** ADR-DKB-001 §3 unchanged.

**Coverage.** `_coverage` reads the symbol's `language` and returns `profile`; reasons for `c`: `indirect-reference`, `unread-file`, `dynamic-import`, `ambiguous-abi-name`; for `cpp`: today's set plus the last two. The limit text is per profile: the C text names macro-generated definitions, function-pointer and ops-table calls, vendored and generated paths, error-return codes; the C++ text is `CXX_LIMITS_TEXT`. A Python pack carries neither.

**Dialect.** The scanner tolerates a closed table of dialect keywords (`__attribute__`, `__asm__`, `__interrupt`, `__irq`, `__ramfunc`, `__root`, `__weak`, `__packed`, `__svc`, and others added only with a fixture). The scanner calls no compiler. `truth_clang.py` takes `-D` and `-I` flags for verification.

## 3. Data contract (D8)

**Boundary record** (emitted by an extractor, never written to the graph):

| Field | Meaning |
|---|---|
| `direction` | `export` or `import` |
| `abi_name` | the name on the wire: C symbol, `PyInit_` module name plus table name, pybind11 module plus Python name |
| `mechanism` | `extern-c`, `ctypes`, `cffi`, `pyc-api`, `pybind11` (`jni` reserved) |
| `file`, `line` | where it is written |
| `symbol` | export: the defining Symbol, absent for a lambda; import: the calling Symbol |
| `dynamic` | true when the name is not a literal |

**Resolver.** Link an import to an export when: both records are in the repository; the `abi_name` matches exactly one export of that mechanism family (`extern-c` imports match `extern-c` exports, `ctypes` and `cffi` imports match C exports, `pyc-api` and `pybind11` imports match module exports); the export has a defining Symbol. A name with two exports is unresolved with reason `ambiguous-abi-name`; a lambda export with `lambda-binding`; a `dynamic` import is unresolved, marks its Symbol `incomplete_reasons` `dynamic-import`, and adds to a repository count that every exported symbol's pack states. `[ASSUMPTION]` a literal `dlsym(h, "x")` is also unresolved in this slice. A name with no export in the repository is not a boundary and is not counted (the library-name rule of ADR-DKB-001 §3).

**Edge.** `CALLS`, `source` the mechanism, `evidence_ref` `<path>:<line>`, confidence `[ASSUMPTION]` `extern-c` 0.9, `ctypes` 0.8, `cffi` 0.8, `pyc-api` 0.8, `pybind11` 0.8. An older same-pair edge from another rule is replaced, not duplicated. `CALLS_API` is unchanged and stays for network boundaries.

**Export flags.** `abi_exported` is true for a definition with `linkage` `c` and no `static`, for a `PyInit_` name, for a JNI name (`Java_<pkg>_<Class>_<method>`) and `[ASSUMPTION]` for a function listed in a `PyMethodDef` table even when `static`. `boundary_kind`: `c-abi`, `jni`, `pyinit`, `pyc-method`, `pybind11`. A C++ method is never exported.

**Pack.** For `abi_exported` symbols the coverage reply keeps `complete` as computed and adds `qualified` true, `languages_read` (languages the build read) and `boundary_kind`. The text reads: "**Complete for the languages read** (c, python). Callers may exist in languages not read (<kind>)." plus the dynamic-lookup count when non-zero. A `static` symbol keeps the strong Complete sentence.

**ConfigKey.** Kconfig `config`, `menuconfig` and `choice` entries `DECLARE` `kconfig:CONFIG_NAME`; `CONFIG_NAME` in masked C text under `#if`, `#ifdef`, `defined()`, `IS_ENABLED()` or a plain use gives `READS` (Symbol inside a function, else File). `.dts` labels and `DT_NODELABEL(label)` do the same for `devicetree:<label>`. No value is stored. `[ASSUMPTION]` key names.

## 4. Ontology change

Only: the `language`, `linkage`, `abi_exported`, `boundary_kind` rows in the Symbol property table; `language`, `consumed_by_cpp` in File; the `ConfigKey` description (adds Kconfig and devicetree options); the `CALLS` `source` values. No node type and no edge verb.

## 5. Verification

C++ and C: `bench/cpp/truth_clang.py` and `quality.py` (compiler truth; `quality.py` gains a split by language and by edge `source`). Python and C: fixtures with a labelled truth and `bench/boundaries/check.py`; its own precision (floor 1.0 on the deterministic fixtures). Header and `CONFIG_` counts against independent regex counts. Floors follow ADR-DKB-001 §7 (recall: first measurement minus 0.02; precision: 0.95 initial, `[ASSUMPTION]`).

## Consequences

- A C pack stops talking about overloads and receivers; it names the limits that apply to C.
- Most non-static C functions now print the foreign-callers note, including in C-only repositories. `[ASSUMPTION]` accepted as the owner stated the rule; story 2.7 measures the noise and the owner may narrow it.
- Some packs that said the strong Complete now say the qualified one: the honest outcome of the defect fixture, not a regression.
- A `.h` with only `::` is now C where it was C++.
- Existing cross-language edges change `source` (from `cpp-unique-free` to `extern-c`) and confidence; consumers filtering by source see the change.

## Open

- Whether the exported-symbol note is limited to symbols declared in a header or named by an import record.
- A real Python and C corpus for the precision measure.
- The extractor and resolver module layout, for `bmad-architecture`.
