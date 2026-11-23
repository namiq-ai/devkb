# Look-back on 0.2.15 and plan for 0.2.16 (2026-11-23)

Written for the owner, to carry technical lessons into what devkb contributes. Figures are from the files named; where a figure is a pointer and not a result, it says so.

## 1. Objective, and why

devkb's value claim is that an agent given the graph spends fewer steps and gets more right. 0.2.15 set out to make that claim measurable and true in three places:

| Objective | Why | Result |
|---|---|---|
| **C and C++ reach Supported** (#123, #124) | The graph is only worth asking if its edges are right; C/C++ was the weakest language and the only one with no precision measurement an agent would care about. | **Met, with caveats.** Adjudicated precision 599/600; recall 0.70 to 0.98 against the compiler; Zephyr 113.5 s. One judge, not independent. |
| **Make the benchmark able to see an agent use devkb** (#369, #386, #420, #337) | Until 0.2.14 the permission checker refused every devkb command a benchmark agent tried, and a ticket's location in the text let agents skip navigation. A null result then meant nothing. | **Met.** Agents can run devkb, the location can be hidden, and each run records which entry points it had. |
| **Exact spans and fewer wrong answers on the read path** (#418, #389, #393, #409) | `outline` and `symbol --source` are only a substitute for reading when the lines are exact. | **Met for TS/TSX spans; hook answers widened.** |

What 0.2.15 did **not** do: show that agents use devkb more or finish faster. Hidden-location batches of 7 runs per arm: #386 acceptance none 5/7, main 6/7, bothuser 7/7 (cost $0.148, $0.165, $0.169); #418 all 7/7 (cost $0.440, $0.420, $0.416). Devkb queries by agents: 0 of 21 runs in #386 and 2 of 21 in #418. At n=7 none of these differences is distinguishable from noise.

## 2. Technical lessons

1. **A truth-based number is a lower bound; a judged sample is a different instrument. Report both and name the convention.** fmt's precision against the compiler was 0.387 while the judged sample found 99/100: the compiler cannot see calls in uninstantiated templates. Scorer conventions moved results by more than any extractor fix did (overload-aware mapping took leveldb's constructor edges from 66% to 90%; excluding lambda internals moved fmt symbol recall 0.938 to 0.962). Every convention is now written next to its number.
2. **The first adjudication failed, and that is why it was worth doing.** Precision looked fine on the compiler's view; reading 600 edges found four defect classes (macro expansion across files that cannot see the macro, local lambdas, `using` names, `T x(*this)`). A metric the extractor's author cannot fail is not a gate. The remaining weakness is that the same author judged: two of my first fmt verdicts were wrong, found only by rereading source.
3. **Union over configurations invents calls; intersection loses real ones.** A macro with several definitions (Zephyr's logging) produced 241,020 edges, 84,605 of them pointing at back ends no single build calls. Intersecting the visible variants cut them to 30,566. Precision-first is the right default for an agent that trusts an edge, but the removed edges were not sampled, so the recall cost on Kconfig-heavy code is unknown.
4. **A guard that says "never" needs its exception written down.** "Never link a C library name across files" was correct for a stub and wrong for a freestanding libc, and the two look the same in shape. It took a measured recall miss (autoas 0.747) to expose it; the rule became a path convention, recorded in ADR-DEVKB-008 §3 with the owner's approval.
5. **Performance regressions hide in repeated work, and a profiler can point at the wrong function.** The macro rule parsed the same body 919,113 times (+29 s on Zephyr). cProfile attributed the cost elsewhere on an earlier run; phase timers and call counts found it. One `lru_cache` removed it (130.7 s to 113.5 s). Always compare edge counts before and after an optimisation (identical here).
6. **Most of the measurement loss was in the harness, not in devkb.** A work directory under `~/.claude` made every run invalid; a leaked `POLICY_ARMS` made a base suite red; a stale monitor shell stalled a batch for 10 hours; contaminated runs came from switching branches under a running batch. None showed up as a test failure. Cheap defences: work dirs under `~/.cache`, `suite_env()`, separate worktrees per batch, and checking process lists before assuming a batch is running.
7. **Agents choose the shell and then do not choose devkb.** Over the whole 0.2.15 window devkb was 2% to 7% of navigation calls in working sessions, and the hook answered 4.7% of decisions there (7.8% in benchmark runs). `stale-graph` was 31% of decisions, largely the harness committing after the graph build; `not-complete` was 47% of working-session decisions. Value therefore has to come from answers delivered without the agent choosing, and from the graph being fresh and Complete often enough for the hook to answer.
8. **Cost estimates and checklists need the same discipline as code.** My estimate for the #418 experiment was low by about 40% and was corrected before it ran; the per-ticket checklist (hidden check, two arms, two-way review, Execution result) is still skipped under time pressure and backfilled.

## 3. The integration guide you asked me to check

I had not read `devkb + Claude Code Integration Specification & Repository Wiring Guide.md` before this request. I have now, against the repository. Its strategy is sound and matches what the data says (selective answers, no default router, no passive pack on `Read`, size budgets, no full rebuild in a hook). **Its wiring does not match this repository, and some numbers are out of date:**

| Guide says | Repository |
|---|---|
| `python3 -m devkb.hook session-start / pre-search / post-tool-telemetry / prompt-router` | `devkb/hook.py` accepts only `pre-edit`, `prompt` and `context` (`devkb hook` prints that usage). The search guardrail is `scripts/devkb_guardrail.py` (Pre) and `scripts/devkb_guardrail_post.py` (Post), wired in `.claude/settings.json` with matcher `Read|Grep|Bash`. |
| `python3 -m devkb.testing.hook_replay --fixtures tests/fixtures/hook_sessions.jsonl` | Neither exists. The replay is `bench/policy/hook_replay.py`; there is no such fixture file. |
| `policybench.py score --run-dir bench/runs/latest/` | `score` takes a ticket number (`policybench.py score 386`). |
| `DEVKB_ROUTER=0` is the default; the check must print `NO CONTEXT` | The router returns nothing (`None`) only when `DEVKB_ROUTER` is exactly `0` (`router.py:341`); with the variable unset it is on. `NO CONTEXT` is not hook output: it is what a headless `claude -p` model said in an earlier experiment (`docs/analysis/improvement-plan-data-loop.md:16`), so the guide's verification step would never match. |
| Router costs `+2.6` turns and `+$0.09` | Superseded in `docs/analysis/workflow-router-benchmark.md:206`: **+0.8 turns and +13% cost against `rmain`**; the +2.6 compared against a different baseline. |
| `1,231` tests | 1,506 pass on main. |
| Recall `0.74 -> 0.83` | QB1 `pack file` 0.74 (0.69-0.80) to `pack file` + `pack refactor` with mentions 0.83 (0.77-0.88), precision 0.63 (`docs/analysis/qb1-baseline.md:62`); the intervals nearly touch, so it is a pointer, not a settled gain. |
| `.mcp.json` runs `python -m devkb.mcp_server` | This repository deliberately has no default MCP use (12 tool definitions cost about 3k tokens per call; agents chose the shell anyway: `docs/analysis/devkb-none-mcp-cli.md`); the shipped `.mcp.json` uses `devkb mcp --toolset lean-pack`. |

I did not verify its `96 live runs`, `-18% context`, `+0.15 held-out symbol recall` or `12-13 s` index time against a source; treat them as unchecked. Recommendation: **correct the guide to the repository (do not implement subcommands the guide invents), and keep its two real ideas as 0.2.16 candidates:** a `SessionStart` index-status check (Layer 5) and a pre-edit pack with the 800-token cap (the shipped `pre-edit` hook has a 6,000-character limit).

## 4. Plan for 0.2.16

Principle: spend the milestone where it moves what an agent gets without choosing, and stop spending on null-effect batches. Priorities, each with a falsifiable finish:

| # | Theme | Tickets | Done when |
|---|---|---|---|
| 1 | **Fresh graph, so the hook can answer** | #411 incremental update; harness builds the graph after the policy commit (file it); #390/#391 follow-ups on `not-complete` | `stale-graph` below 5% of benchmark decisions; hook answered share measured on the same tickets before and after, not across batches |
| 2 | **Close the C/C++ caveats** | independent re-judgement of the 134 hand verdicts; sample 100 of Zephyr's 84,605 removed macro edges; make `_HOST_DIRS` configurable per project; fmt recall margin (0.703 vs 0.70) | a second judge agrees on at least 95% of verdicts; the removed-edge sample says how many were true calls; one real repository outside the six checked |
| 3 | **TypeScript/JavaScript Supported (#313)** | owner accepts or edits SPEC-DKB-008 first (it is `proposed`); then its stories in order, spans (#418) already done | each story's N-requirement measured on the F7 repositories before the README row moves |
| 4 | **Guide reconciliation** | fix the guide to the repository; a `SessionStart` status check and a capped pre-edit pack as two small tickets with a replay-based measurement | replay shows the answer size under the cap and no change in answered share; no new agent runs required |
| 5 | **Measurement hygiene** | harness guards for the 0.2.15 failures (work-dir location, env leak, stale monitor); thresholds ticket #368 | a batch refuses to start when a guard trips; no more null 7-run agent batches unless the replay or QB gives a reason to expect an effect |
| 6 | **Backlog robustness** | #77, #75, #53, #67, #68, #56 | each closed with a regression test |

Out of scope unless the owner asks: turning on the tool entry point (0 to 2 queries in 35 runs), the workflow router by default, new graph schemas.

Open decisions for the owner: accept SPEC-DKB-008 as written; whether to fund an independent judge for the C/C++ sample; whether the guide is to be corrected or treated as a target design.
