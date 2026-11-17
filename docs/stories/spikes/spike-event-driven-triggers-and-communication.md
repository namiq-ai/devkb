---
id: 2
type: spike
title: "How does the graph know that a function with no caller is a handler something else triggers?"
parent: none
covers: []
after: []
assignee: ""
refined: false
hitl: true
risk: medium
---

# How does the graph know that a function with no caller is a handler something else triggers?

## Description

**Not for now.** Filed 2026-11-16 by the owner's request; nothing here is built until the owner starts it.

**Who is blocked and why.** An agent (or a person) asking whether a function is dead, or who calls it, gets "no callers" for an interrupt service routine, a timer callback, a work item, a thread entry, a signal handler or a driver operation. Those are not dead: a registration site names them and the runtime calls them. Today they are counted as unresolved indirect references (ADR-DKB-001 §3), so the pack says Incomplete without saying why or by whom.

**Evidence** (Zephyr, owner's survey, to be re-run at the pinned commit in step 1):

| Kind | Files | Registration sites named |
|---|---|---|
| IRQ | 1,072 | `IRQ_CONNECT`, `irq_connect_dynamic`, `ISR_DIRECT_DECLARE`; names `*_isr`, `*_IRQHandler`: 1,483 |
| timers and alarms | 180 | `k_timer_init`, `K_TIMER_DEFINE`, `SetRelAlarm` |
| work queues | 601 | `k_work_init`, `K_WORK_DEFINE` |
| threads and tasks | 779 | `k_thread_create`, `K_THREAD_DEFINE`, `pthread_create`, `TASK()` |
| POSIX signals | | `signal`, `sigaction` |
| callback registration | 1,084 | |
| device operation tables | 2,147 | `DEVICE_DT_INST_DEFINE`, `*_driver_api` |
| init hooks | 451 | `SYS_INIT` |
| shell and test tables | 1,890 | |
| IPC and messages | 332 (autoas: 52) | `k_msgq`, `mqueue`, `Com_Send`, `SoAd`, `SomeIp`, `Rte_Write` |

**The question.** How do we mark handlers so "0 callers" is not read as "dead", and show who triggers them? The proposed answer, to confirm or replace:

- **A table-driven knowledge base of registration APIs**: one row per API with the position of the handler argument (or the named field of an ops struct), the `trigger_kind` (`irq`, `timer`, `work`, `thread`, `signal`, `callback`, `device-op`, `init`, `table`), and the form (call, macro with the handler as an argument, struct-field initializer). A row is added only with a fixture line.
- **A TRIGGERS-style relation**: `TRIGGERS` from the registrar Symbol (or the File, for a file-scope macro such as `K_THREAD_DEFINE`) to the handler Symbol, with `trigger_kind`, `source` the row id, and `evidence_ref` `<path>:<line>`. A handler that is resolved by the same unique-name rule as any call (SPEC-DKB-002 D8: unique, in the repository); otherwise unresolved and counted.
- **Handlers marked as entry points**: `entry_point` true and `entry_kind` the trigger kind. `callers` and any "unused" answer say "no direct callers; triggered by `<kind>` at `<path>:<line>`" instead of an empty list. A registration that explains an indirect reference removes that reference from the unresolved count, as SPEC-DKB-002 story 2.5 does for a `PyMethodDef` table.
- **Naming is weak evidence**: a function named `*_isr` or `*_IRQHandler` with no row is marked `entry_point` with source `naming` and low confidence, never given a `TRIGGERS` edge, and never makes a pack Complete.
- **A per-project extension point**: a tracked file at the repository root (pick: `devkb-registrations.yaml`, read with the existing `pyyaml` dependency) holding project rows in the same shape, merged over the built-in table; a row names its macro, handler position and kind. A project macro with no row stays an unresolved indirect reference.
- **IPC and messages** are a second step: a send and a receive on the same queue object are two ends of one relation, which needs either a new node (a channel) or an edge property. This ticket decides whether to include it, with the 332 and 52 counts as the case.

## Approach

1. Re-run the survey with a script importing nothing from `devkb`; commit the counts. Time box: 4 days `[ASSUMPTION]`.
2. Write the registration table for Zephyr and autoas first (the eight kinds above) with one fixture line per row.
3. Prototype the relation and the entry-point marks on a branch (no merge). Handle the three forms, including designated initializers in `*_driver_api` structs and `DEVICE_DT_INST_DEFINE`.
4. Measure on Zephyr: of the functions with no direct caller, how many gain a `TRIGGERS` edge; false-link rate on a hand-labelled sample.
5. Decide the questions below and write the ADR draft. A new verb `TRIGGERS` and new properties need an Accepted ADR (`devkb/ontology.md`, ADR-SDP-DEVKB-001).
   - Does a registered handler's pack become Complete? Pick: Complete for the languages read, qualified like an exported symbol (SPEC-DKB-002 story 2.1): the runtime may also call it by means not in the table.
   - Where does the extension file live and is it validated (unknown kind, missing handler position fails loudly)?
   - Are IPC channels in or out of the first build?
   - Generated registrations (RTE, syscall lists) are in the sibling ticket on generated code; say which of them this table can already read.
6. TL and the owner review; the owner decides whether to build.

## Acceptance Criteria

1. **The survey is reproducible and its counts are committed**
   Verify: `python3 bench/triggers/survey.py ZEPHYR_DIR AUTOAS_DIR` prints the counts of the table above; output in the spike's result file.
2. **The registration table covers every kind in the table and is fixture-backed**
   Verify: `devkb-registrations` built-in table in the prototype has a row per API named in the table; `pytest tests/test_registrations.py` fails for a row with no fixture line.
3. **The relation and entry-point marks work on the corpus, with measured precision**
   Verify: the result file shows, on Zephyr, the number of no-caller functions before and after, the number explained by `TRIGGERS`, and on a labelled sample of 50 handlers the wrongly linked ones, each reported separately; a wrong link is a model failure.
4. **A pack and a `callers` reply state the trigger**
   Verify: rendered fixtures show "no direct callers; triggered by irq at ..." for an `IRQ_CONNECT` handler, the same for a work item and a device operation; a function named `*_isr` with no row is marked by naming only and its pack is not Complete.
5. **A project can add a registration macro without changing devkb**
   Verify: a fixture repository with `devkb-registrations.yaml` naming `MY_REGISTER(handler, ctx)` links its handler; a malformed row fails the build with the row named.
6. **The answers to the questions of step 5 are recorded with their consequences**
   Verify: an ADR draft `docs/adr/ADR-DEVKB-0NN_event-triggers.md` with status Proposed; TL and the owner accepted it, recorded in its status line.

## References

- spec — `docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md`, §Approach (unique-name rule, qualified Complete, per-profile coverage)
- decision — `docs/adr/ADR-DKB-001_c-cpp-support.md`, §3 (indirect references) and §4 (when a pack may say Complete)
- ontology — `devkb/ontology.md`
- sibling — `_bmad-output/backlog/spike-generated-code-and-preprocessing-as-graph.md`

## Notes

- Assumption: time box 4 days; the owner may change it.
- Assumption: the relation is named `TRIGGERS` as the owner wrote "TRIGGERS-style"; the final name is the ADR's.
- Assumption: the extension file is `devkb-registrations.yaml` at the repository root; `.devkb/` is the regenerated graph directory and is not used.
- Open question: counts for POSIX signals are not given by the owner; the survey fills them.
