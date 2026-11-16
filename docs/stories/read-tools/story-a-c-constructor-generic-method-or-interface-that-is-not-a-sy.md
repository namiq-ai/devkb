---
id: 2
type: story
title: "A C# constructor, generic method or interface that is not a Symbol is named, not denied"
parent: epic-language-readiness
covers: [R10]
after: ["1.2", "1.6", "1.8"]
hitl: false
risk: medium
---

# A C# constructor, generic method or interface that is not a Symbol is named, not denied

## Description

The C# extractor misses 12.5% of methods (generic and extension methods among them), 29% of constructors, and has no `interface` Symbols. A bare "no symbol named Loader" for a class that exists would send an agent to re-implement it. Backlog 4 fixes the data (not for now); this story makes the tools truthful meanwhile on FX-CS.

## Requirements

1. **A miss in a C# repository carries the C# note** (R10)
   **Given** FX-CS where `Load<T>` and `ILoader` and the `Loader` constructor are in `not_indexed`
   **When** `symbol "Load<T>"`, `symbol ILoader` and `symbol ".ctor"` run
   **Then** each reply says `no symbol named` and `C# constructors, generic and extension methods and interfaces are not indexed`, then shows the first 3 `uses` hits of the name, so the definition line is visible

2. **The note appears only where it can apply** (R10)
   **Given** FX-PY and FX-C
   **When** a missing name is searched
   **Then** the reply has no C# note; the note is chosen by the extensions of the files the query could belong to (`under`, `path::name`) or, with none, by the languages present in the graph

3. **An outline says what it leaves out** (R10)
   **Given** `outline src/Loader.cs` on FX-CS
   **When** it runs
   **Then** the header adds `constructors, generic methods and interfaces are not indexed` and the listed methods and the property are exact

4. **A found method is not annotated** (R10)
   **Given** FX-CS `Load(string)`
   **When** `symbol Load` runs
   **Then** the record has no note about missing members (a hit is a hit)

## Boundaries

- Must not change: C# ranges (99.9 to 100% exact).
- Not here: making them Symbols (backlog 4).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 8
- backlog — _bmad-output/backlog/story-csharp-constructors-generic-methods-and-interfaces-become-symbols.md
