---
id: 5
type: story
title: "symbol ranks symbols that share a name and filters by kind and path"
parent: epic-core-read-tools
covers: [R4]
after: [3]
hitl: false
risk: low
---

# symbol ranks symbols that share a name and filters by kind and path

## Description

10 to 26% of short names map to several symbols (leveldb 26%). This story gives the order of ADR-DEVKB-010 section 3.4 and the filters `kind`, `under` and `limit`, so the match an agent wants is first.

## Requirements

1. **Production code ranks before test code** (R4)
   **Given** FX-PY with `get` in `app/config.py`, `app/cache.py` and a test-file helper `get` in `tests/test_config.py`
   **When** `symbol get` runs
   **Then** the two `app/` records come before the test record

2. **A shallower qualified name ranks first, then more callers, then path** (R4)
   **Given** FX-CPP with a free `get`, `kv::get` and `kv::Store::get`, where callers are 1, 5 and 2
   **When** `symbol get` runs
   **Then** the order is free `get`, `kv::get`, `kv::Store::get` (depth first); for two symbols of equal depth the one with more callers is first; for equal callers the lower path is first

3. **`kind` and `under` filter before tiering** (R4)
   **Given** FX-PY where `Config` is a class and `config` is part of a module path
   **When** `symbol config kind=class` and `symbol get under=app/cache` run
   **Then** the first returns only `Config`, and the second only `Cache.get`; an unknown `kind` value gets a one-line reply listing the kinds present in the graph

4. **`limit` cuts after ranking and says how many were not shown** (R4)
   **Given** FX-PY and `limit=1` for `get`
   **When** `symbol get limit=1` runs
   **Then** one record is shown, the first by the rank rule, and the last line reads `(2 more matches)`; the default limit is 8

## Boundaries

- Must not change: which tier answers (1.3, 1.4).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 3.4
- analysis — docs/analysis/read-tools-analysis.md, section 4 (shared short names)
