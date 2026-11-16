---
id: 3
type: story
title: "symbol finds a qualified name, a suffix, a glob or a regular expression"
parent: epic-core-read-tools
covers: [R2]
after: [2]
hitl: false
risk: medium
---

# symbol finds a qualified name, a suffix, a glob or a regular expression

## Description

Tiers 2 to 5 of ADR-DEVKB-010 section 3.1, as pure functions over `CompactIndex` so each tier is unit-testable. A query is tried tier by tier and the first tier with hits decides the answer; the reply says which tier (`how`).

## Requirements

1. **Separators `.`, `::` and `#` are one separator** (R2)
   **Given** FX-CPP with `kv::Store::get` stored as `kv.Store.get`, and FX-PY with `Config.get`
   **When** `symbol "kv::Store::get"`, `symbol "kv.Store.get"` and `symbol "Config#get"` run
   **Then** each finds its symbol with `how qualified`

2. **A file prefix restricts the match** (R2)
   **Given** FX-PY where `get` is in `app/config.py` and `app/cache.py`
   **When** `symbol "app/cache.py::get"` runs
   **Then** only the `Cache.get` record is returned, `how qualified`; a prefix that matches no file gives `no symbol named` with the reason `no file ends with "..."`

3. **A suffix of the qualified name finds a deeper symbol** (R2)
   **Given** FX-CPP
   **When** `symbol "Store.get"` runs
   **Then** `kv.Store.get` is returned with `how suffix`, and a one-segment query never reaches this tier when tier 1 had a hit

4. **A glob matches the short name** (R2)
   **Given** FX-PY
   **When** `symbol "load_*"` and `symbol "?et"` run
   **Then** the first returns `load_config` and the second `get`, both `how glob`; `symbol "*"` is refused with `glob too broad` and no list

5. **A regular expression is explicit or auto-detected** (R2)
   **Given** FX-PY
   **When** `symbol "re:^load_"`, `symbol "^load_.*g$"` and `symbol "Config|Cache"` run
   **Then** each is evaluated as a case-insensitive regular expression on the short name with `how regex`; a query with a dot or `::` and no regex character is never a regex

6. **An invalid expression is an error, not a fallback** (R2)
   **Given** the same build
   **When** `symbol "re:(["` runs
   **Then** the reply is one line `bad regular expression: <reason>` and no other tier is tried

7. **The first tier with hits wins** (R2)
   **Given** FX-PY where `get` exists
   **When** `symbol get` runs
   **Then** the matches are all `how exact`, and no glob, regex or fuzzy match is added to them

## Boundaries

- Must not change: tier 1 behaviour of story 1.1.
- Not here: prefix, substring and fuzzy tiers (1.4); ordering of ties (1.5).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 3.1

## Notes

- Assumption: a regular expression is auto-detected by one of `^ $ + ( ) [ ] { } |` or a backslash.
