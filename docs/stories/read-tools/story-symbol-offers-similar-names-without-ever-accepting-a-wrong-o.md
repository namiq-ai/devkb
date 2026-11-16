---
id: 4
type: story
title: "symbol offers similar names without ever accepting a wrong one"
parent: epic-core-read-tools
covers: [R3]
after: [3]
hitl: false
risk: high
---

# symbol offers similar names without ever accepting a wrong one

## Description

Tiers 6 and 7 of ADR-DEVKB-010 section 3, the riskiest part: a fuzzy match is a guess, and the measurement says word overlap alone accepts a name that does not exist 35 to 50% of the time, edit similarity at a threshold of 55 only 1 to 7%. So prefix and substring are deterministic, a fuzzy match is labelled `similar` with its score, and below 55 the reply is "no symbol named", with suggestions that are not matches.

## Requirements

1. **Prefix, then substring, are labelled as such** (R2)
   **Given** FX-PY
   **When** `symbol load_` and `symbol onfig` run
   **Then** the first returns `load_config` with `how prefix`, the second `load_config` with `how substring`; a query under 3 characters is never a substring query

2. **One typo is found and labelled similar** (R3)
   **Given** FX-PY
   **When** `symbol load_confg` runs
   **Then** `load_config` is returned with `how similar NN` where NN is at least 55, and the reply's first line says the match is approximate

3. **A name below the floor is never a match** (R3)
   **Given** FX-PY
   **When** `symbol reticulate_splines` runs
   **Then** the reply is `no symbol named "reticulate_splines"` followed by `closest names (not matches):` and at most 5 names with path and score; the reply holds no signature, no range and no source for them

4. **Word overlap proposes, it never accepts** (R3)
   **Given** FX-PY where `load_config` exists and the query is `config load`
   **When** `symbol "config load"` runs
   **Then** `load_config` appears under `closest names (not matches)` unless its edit-similarity score is 55 or more, and is never returned as a match on word overlap alone

5. **The false-accept rate is measured** (R3)
   **Given** the 200 invented names and the four graphs of `bench/readtools/name_matching.py`
   **When** the story's check runs the real resolver over them
   **Then** the share accepted as a match is at most 7% on each graph, the result is committed in `docs/analysis/read-tools-fuzzy.md`, and the exact-name and wrong-case cases still succeed at rank 1 in at least 98% of the sample

6. **A fuzzy tier is never reached when an earlier tier hit** (R2)
   **Given** FX-PY
   **When** `symbol get` runs
   **Then** no `similar` record appears next to the exact ones

## Boundaries

- Must not change: the answers of tiers 1 to 5.
- Not here: ranking of ties (1.5).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 3.1, 3.2, open question 1
- analysis — docs/analysis/read-tools-analysis.md, section 4

## Notes

- Assumption: score is the edit similarity of lower-cased short names on a 0 to 100 scale, the one the experiment script measures.
- Open question: word overlap proposing but not accepting is the PO's reading of D2 (open question 1 of the ADR); the false-accept check settles whether a score floor for word overlap is also needed.
- Check beyond the criteria: run the 200-name check on a fifth graph the build has not seen.
