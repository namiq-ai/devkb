---
id: 3
type: story
title: "Overloads that share one node say so"
parent: epic-language-readiness
covers: [R10]
after: ["1.2", "1.7", "1.8"]
hitl: false
risk: medium
---

# Overloads that share one node say so

## Description

In C# and C++ several overloads of one name share one graph node, and its range is the last definition. A source reply for `put` would show one overload as if it were the function. The tool cannot split the node, but it can count the definitions in the text and say the range is shared.

## Requirements

1. **A shared node says it is shared** (R10)
   **Given** FX-CPP `kv::Store::put(int)` and `put(std::string)` as one node, FX-CS `Load(string)` and `Load(Stream)` as one node
   **When** `symbol put` and `symbol Load` run
   **Then** each record carries `shared range (2 overloads)`, the number found by scanning the file text for definitions of the name inside the node's class, and the range shown is the stored one

2. **Source says which overload it shows** (R10)
   **Given** the same
   **When** `symbol put source=True` runs
   **Then** the block is headed `one of 2 overloads; stored range is the last definition` and the other overloads' start lines are listed (`other definitions: L12, L30`) without bodies

3. **A node with one definition is not annotated** (R10)
   **Given** FX-CPP `kv::Store::get` and FX-PY (no shared nodes)
   **When** `symbol get` runs
   **Then** no `shared range` text appears, on a C++ or any other file

4. **The count never exceeds what the text shows** (R10)
   **Given** a declaration in `store.hpp` and a definition in `store.cpp` of the same function (not an overload)
   **When** `symbol` runs
   **Then** the reply does not call them overloads (a declaration with no body is not counted)

## Boundaries

- Must not change: the stored range of a node.
- Not here: splitting nodes per overload (a graph change).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 1, 8
- analysis — docs/analysis/read-tools-analysis.md, section 2 finding 5
