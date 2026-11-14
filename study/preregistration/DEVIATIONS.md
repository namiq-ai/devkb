# Deviations from PREREGISTRATION.md (frozen 2026-11-14T08:47:46Z, sha256 d43bd069ff8abd89…)

All made before any confirmatory agent run.

**D1 (2026-11-14T08:53Z) Truth by import path instead of unique names.** The pre-registered generator
(`oco_tasks.py`, truth `workflow_tasks.callers_of`) keeps only functions whose names are defined once in the
repository. On Repository C (Netflix Dispatch, dozens of `service.py` modules defining `get`/`create`) it produced
one task. The study uses `devkb/bench/module_truth.py` and `confirm_tasks.py` instead: a call is resolved through the
caller file's imports to the module that defines the function, targets are module-level functions, and a chain is kept
only when no method stands on it except a route handler at its end. Applied identically to all four repositories.

**D2 (same time) One-hop error traces allowed.** The generator required two or more production functions between
raiser and handler; the pre-registered task definition ("an error message raised once in non-route code ... every
route handler that reaches it") does not. One-hop chains are admitted; one task per raising function.

**Consequence.** 30 tasks (A 7, B 8, C 8, D 7): 15 change-impact, 13 refactor, 2 error-to-handler. Fewer than the
48 planned: literal error messages in these repositories are mostly raised in methods or built with format strings.
H4 (error-to-handler cost) has two tasks and is reported as underpowered; the exploratory error tasks (four, Repository
A) are reported separately as exploratory.

**D3 (2026-11-14T13:12Z) Runs stopped by the account's usage limit are re-run.** The pre-registration says no
run is repeated and invalid runs score 0. On 2026-11-14, 763 runs did not run the task at all: the CLI returned
"You've hit your 5-hour limit" at cost $0 in one turn (614 confirmatory: Sonnet on C and D, all of Haiku; 16 of the
ablation baseline; 133 of the process study). They measure the account, not an arm, so they are kept apart in
`runs/_limit-failed/` and the affected cells are re-run in full with the same tasks, seeds and code. The harness now
waits and re-runs a run whose output is a usage-limit error (`run_one`, `limit_retries` recorded per row); a run in
which the agent attempted the task is never repeated. No completed cell was changed.

**D4 (recorded after the analysis) How H3 is tested.** The pre-registration states H3 as "core costs no more than
plain" and says "Holm correction across H1 to H4 (cost)", without saying how a no-worse claim enters a family of
one-sided superiority tests. `analyze.py` (written 2026-11-14T08:54Z, after the freeze and before any run) judges H3
on its interval and point estimate and leaves it out of the Holm family. The paper reports both readings: supported
as stated (cost saved 15%, 95% CI 7–22%, quality non-inferior); not significant as a superiority claim inside the Holm
family (adjusted p = 0.13, over H1, H2, H3 and the two H4 tests). This choice was not made after seeing the result,
but it was not pre-registered either.

**D5 (recorded after the analysis) The ablation's plain baseline came from a later session.** Under D3 the plain
baseline of the ablation was re-run hours after its four cells. The same arm on the same six tasks cost $0.57, $0.41
and $0.55 in three sessions. The pre-registered quantities (main effects and interaction) compare cells that ran
together and are unaffected; each cell's saving against plain is reported but not interpreted.
