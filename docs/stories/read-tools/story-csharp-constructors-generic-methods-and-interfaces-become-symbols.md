---
id: 4
type: story
title: "C# constructors, generic methods and interfaces become Symbols"
parent: none
covers: []
after: []
assignee: ""
refined: false
hitl: false
risk: medium
---

# C# constructors, generic methods and interfaces become Symbols

## Description

**Not for now.** Filed 2026-11-16 by the owner's request; nothing here is built until the owner starts it. The read tools work without it: on a C# miss they say constructors, generic methods and interfaces are not indexed and show the `uses` hits (story 2.2 of the read-tools initiative).

**Who is blocked and why.** An agent asking `symbol` for a C# constructor, a generic or extension method, or an interface cannot be answered from the graph, and `callers`, `pack` and `outline` cannot see them either. 12.5% of methods and 29% of constructors are missing, and no `interface` is a Symbol.

**Evidence** (analysis section 2, C# rows: MediatR recall 0.85, FluentValidation 0.83):

```
python3 bench/readtools/range_accuracy.py <MediatR checkout> <MediatR graph dir> csharp
python3 bench/readtools/range_accuracy.py <FluentValidation checkout> <FluentValidation graph dir> csharp
```

report recall 0.85 and 0.83 against tree-sitter definitions, and the missing definitions are constructors, generic and extension methods, and interface declarations.

**Terminal state.** C# constructors, generic and extension methods and interfaces are Symbols with exact ranges; recall on both repositories is at least 0.95 and precision does not fall.

**Scope boundary.** In: `csharp_symbols.py` extraction of the three kinds, their `kind` values, their CALLS targets where the existing resolver can link them. Out: splitting overloads that share a node (a separate decision); properties and fields; the `language` property (backlog 5); any new node type or edge verb.

**Where to start.** `devkb/csharp_symbols.py` (the definitions pass that builds `Symbol` dictionaries with `kind`, `name`, `qparts`, `line_start`, `line_end`), then the `add_to_graph` function that writes them.

**Owner rationale.** The tools can only name the gap; closing it makes the graph answer. Not now because the read tools ship honest without it.

## Acceptance Criteria

1. **Constructors, generic methods and interfaces are found**
   **Given** the FX-CS fixture (constructor, `Load<T>`, an extension method, `ILoader`)
   **When** `pytest tests/test_csharp_symbols.py` runs and `devkb symbol ILoader` and `devkb symbol "Load<T>"` are run on the fixture build
   **Then** each is a Symbol with the exact `L<start>-<end>` of its `expected.json` entry

2. **Recall reaches the floor on two repositories**
   **Given** MediatR and FluentValidation rebuilt
   **When** the Evidence commands run
   **Then** recall is at least 0.95 on both, precision at least its present value (0.90 and 0.92), and the end-line exact share stays at least 99%

3. **Existing edges do not get worse**
   **Given** the same repositories built before and after
   **When** `edges.jsonl` is compared
   **Then** every CALLS edge that existed still exists, and the diff lists only added Symbols and added edges

4. **The read tools drop their note for what is now found**
   **Given** the change
   **When** `pytest tests/test_readtools_lang_cs_missing.py tests/test_readtools_fixtures.py` runs
   **Then** the `not_indexed` entries of FX-CS for these three kinds are removed from `expected.json`, and the note's assertions are updated to the kinds still missing

## References

- spec — docs/spec/SPEC-DKB-003_read-tools-for-every-language.md, Gaps GAP-6
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 8
- analysis — docs/analysis/read-tools-analysis.md, section 2 finding 3

## Notes

- Open question: are new `kind` values (`constructor`, `interface`) an ontology change that needs an Accepted ADR (`ADR-SDP-DEVKB-001`)? Check `devkb/ontology.md` before starting.
- Open question: a constructor shares its class's name; `symbol Loader` then returns the class and the constructor: ranking story 1.5 puts the shallower qualified name first, which is the class.
- Assumption: overloads keep sharing one node.
