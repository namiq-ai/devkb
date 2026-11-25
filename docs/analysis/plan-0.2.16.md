# Plan for 0.2.16 (written 2026-11-24, after the 0.2.15 release)

Source documents: `docs/analysis/lookback-0.2.15-and-plan-0.2.16.md` (why), `docs/analysis/hook-optimization-0.2.16.md` (the data behind the hook items), `docs/analysis/hook-map-and-guide-rca-0.2.15.md` (what is wired), `docs/analysis/release-0.2.15.md` (performance check and the tickets it produced), `docs/analysis/cpp-promotion-0.2.15.md` (C/C++ caveats).
Milestone 0.2.16 has 21 open tickets (#313, #411, #422 to #440). Nothing in this plan has been run against an agent.

## 1. What the milestone is for

0.2.15 made C/C++ Supported, made the benchmark able to see an agent use devkb, and shipped. It did not show that agents use devkb more or finish faster: across the #386 and #418 batches (7 runs per arm, location hidden) the tool entry point made 1 query in 14 runs. So devkb's value has to come from **answers given without the agent choosing** (the hook), from a **graph that is fresh and right**, and from **numbers that can be trusted**. 0.2.16 spends its effort there, and stops spending on agent batches that cannot show an effect.

Principles carried over: replay and quality benchmarks before agent runs; every number states its population and its convention; a limit is stated next to the claim it limits; one judge is not a gate.

## 2. State at handoff

| Item | State |
|---|---|
| Release | `v0.2.15` tagged at 78b02eb; GitHub release, PyPI and the release graph published. |
| Open PRs | #444 (hard-coded paths after the move, docs for the runtime layout), #445 (the 7-run #386/#418 results, data only). The checkout is on branch `chore/relocate-devkb-0.2.16`; switch to `main` after #444 merges. |
| Layout | The repository is `/home/namiq/orchestra/devkb` (was `ip/devkb`). Runtime state of the nightly and triage daemons: `/home/namiq/orchestra/runtime/devkb/devkb-nightly` and `devkb-triage` (units set `NIGHTLY_HOME` and `TRIAGE_HOME`; triage's `agent-cwd` is a symlink to `~/.cache/devkb-triage/agent-cwd` because the agent must start outside any git repository). |
| Evidence kept outside git | `run/` (untracked, locally excluded): `run/ip-archive` (results and logs of the old benchmark folders), `run/archives` (14 benchmark archives), `run/0.2.15` (7-run batches, C/C++ truth files, perf comparison, job notes, branch audit, deleted-branch tips), `run/branches-0.2.15-unmerged.bundle` (16 unmerged branches; restore with `git fetch <bundle> 'refs/heads/*:refs/heads/*'` into a clone that has `main`). |
| Branches | 14 local, 3 remote (`main`, `chore/relocate-devkb-0.2.16`, `feat/workflow-router`, a stale leftover of merged PR #401). Remaining local `fix/*` branches are held by old scratch worktrees under `/tmp` and `~/.cache`. |
| Disk | Root disk 70% used after the cleanup (was 99%). `~/.cache/devkb/policy-work*` and `policy-templates` were deleted; the harness rebuilds them (each run directory is about 350 MB, 283 MB of it a private `.venv`). `/var/lib/wazuh-indexer` and `/var/ossec` are unsized (need `sudo`). |
| Known regressions shipped in 0.2.15 | Python builds about +9% after the pre-filter (#441 merged; was +20%); `pack file` +22% to +28% (#433); Zephyr `pack change` +48% and peak memory +9% (#434); C/C++ builds +11% to +13% (#435). |
| Systemd | Timers for `devkb-nightly` (02:00), `devkb-triage` (every 4 h) and `devkb-handle` run from the new paths. Only the guard and path checks were exercised; **check `journalctl --user -u devkb-triage -u devkb-nightly` first**. |
| Claude Code | `~/.claude.json` still holds the trust entry of the old path; the first session in the new folder asks to trust it and to approve `.mcp.json`. Project memory was copied to the new key. |

## 3. Workstreams

Each ticket's body has its reproduce command, expected result and "done when"; this table orders them.

### A. Make the harness trustworthy (do first; everything measured depends on it)
| Ticket | What | Done when |
|---|---|---|
| #440 | The harness refuses to start when a known invalidating condition holds (work dir under `~/.claude` or tmpfs, a batch already running, graph built before the policy commit, HEAD moved). Add the finding that each run copies a private 283 MB venv: share it, and clean work dirs after scoring. | One test per guard (a seeded violation refuses); disk per run measured before and after. |
| #368 | Thresholds that decide what a batch can claim (not in the milestone; add it). | Rule written with the 7-run, 40%, six-ticket numbers of 0.2.15. |
| #436 | Every `python -m devkb.X`, `devkb SUBCOMMAND` and script path in `docs/` and `README.md` resolves; wiring guides carry the commit they were checked at; the integration guide is corrected. | The test fails on a seeded wrong command and passes on main. |
| #430 | Each guardrail log row has `hook_commit`; resolve the two hook copies that run in this repository. | Test; the usage audit splits by commit. |

### B. Hook answers: more questions answered, none wrongly (the main value lever)
Order: #426 and #422 first (they change what is counted), then #423, #424. All four are judged by **replay over the 2,111 logged decisions plus 40 hand-judged answers each**, with the 5% wrong-answer floor of SPEC-DKB-007; an item above it does not ship.
| Ticket | What | Expected effect (from the data) |
|---|---|---|
| #426 | A plain-word search is recorded as text, not `not-complete`. | No behaviour change; the `not-complete` share (28%) is restated. |
| #422 | `locate` asks `symbol`, `read-body` asks `symbol --source`. | Addresses 256 withheld decisions (12%). |
| #423 | Two to eight exact candidates are listed, not withheld. | About +4 points of answered share on 5.3%. |
| #424 | Names that resolve are answered; names that did not are listed as not answered. | Ceiling 6.8% of decisions. |
| #428 | `symbol` finds module-level constants and dictionary keys (check whether an ADR is needed for a new node kind). | Held-out symbol recall before and after (QB); graph size on devkb, click and prefect. |
| #431 | Whether a `Read` span hint is followed (from transcripts; free). | Share with its n; under 25% drops the hint. |

### C. Freshness
| Ticket | What | Done when |
|---|---|---|
| #411 | Incremental graph update: persist per-file results, re-resolve only what changed; equivalent to a full build (a random-edit equivalence test). | Step 1 timing on devkb, leveldb and Zephyr recorded before step 2 is decided. |
| #429 | A stale search starts a detached refresh. Depends on #411. | Stale share on the six hidden-location tickets measured before and after with the same hook version. |

### D. Pre-edit hook (the one open question that may need agents)
| Ticket | What | Done when |
|---|---|---|
| #425 | The pre-edit pack keeps its Incomplete note (15 of 17 over-cap packs lose it today), orders by value, and caps the tests list by rank. | Test; QB1 test recall not lower by more than its interval; packs over 3,200 characters reported before and after. |
| #427 | Decide the Bash policy (as is, write-intent only, compacted) by measurement. Replay first: predicted injected size per candidate on the 0.2.15 transcripts. **The agent batch (arms `none`, `hook`, `hook+preedit`, six hidden-location tickets, 7 runs each, about $20) starts only after #425 merged and #440 guards exist.** | Result states cost, turns, acceptance and queries per arm, and the decision to ship, change or drop. |

### E. Performance regressions from the 0.2.15 release check
| Ticket | What | Done when |
|---|---|---|
| #432 | Python build within 5% of v0.2.14 (pre-filter merged as #441; about +9% remains, spread over small new passes). | Release perf check on click, prefect, mealie. |
| #433 | `pack file` within 10% of v0.2.14: lazy import of `build_symbols` on the query path, cache `_named_by_path`'s parsed trees. | Same check. |
| #434 | Zephyr `pack change` +48%, peak +9%: profile, fix or state the reason; write which measure (`extract` or whole `build`) each bar uses (the harness says 172 s, the 120 s bar was met with `extract` at 113.5 s). | Cause named; bar documented in SPEC-DKB-004 and RELEASING.md. |
| #435 | C/C++ and C# build and symbol-query changes explained or fixed. | A paragraph per row. |

### F. C/C++ caveats from the promotion
| Ticket | What | Done when |
|---|---|---|
| #437 | An independent reviewer re-judges the 134 hand-judged edges, blind. **Needs the owner to name the reviewer.** | At least 95% agreement and disagreements resolved by a third reading; otherwise the README row returns to Partial. |
| #438 | Sample 100 of the 84,605 Zephyr macro edges removed by the visibility rule, outside the four logging back ends. | Share that are true in every configuration, with an interval; over 5% relaxes the rule with a test. |
| #439 | `_HOST_DIRS` configurable per project. | A test that a configured directory changes the result. |

### G. TypeScript and JavaScript (#313)
SPEC-DKB-008 is `proposed`; **the owner accepts or edits it first.** Spans (#418) are done. Then its stories in order, each measured on the F7 repositories before the README row moves. Sizing is the owner's call: it is an eight-story epic, and the plan assumes at most two stories in 0.2.16.

### H. Backlog robustness (unmilestoned, pick if time remains)
#77, #75, #53, #67, #68, #56, #155, #163 (each has its own body).

## 4. Order and critical path

1. **Week 0 (before any new measurement):** the open PRs (#444, #445) merged; check the daemons' first runs; #440, #436, #430, #368.
2. **Hook answers:** #426, #422, then #423 and #424; #428 and #431 in parallel (free).
3. **Pre-edit:** #425, then the replay of #427; the paid batch only after A and #425 are in.
4. **Freshness:** #411 step 1 early (it gates #429); #429 last.
5. **Performance:** #433 and #432's remainder early (small); #434 and #435 profile-first.
6. **C/C++ caveats and #313:** parallel to the above, gated on the owner's decisions below.
7. **Release gate:** `bench/perf_release.py v0.2.15 main` on an idle machine (load under 1.0, not the 2.0 gate that 0.2.15 barely met), full suite, the docs-command test, then the owner's go-ahead to tag.

## 5. Measurement rules for the milestone

- Replay and QB benchmarks decide hook items; agent batches are reserved for #427 (about $20, 7 runs per arm, 40% effect, six tickets, location hidden).
- Report every arm, failed and cut-off runs, and the convention behind each number; name a judge and whether the judge is independent.
- The tool entry point (MCP) and the router stay off; reopen only on new evidence.
- No new graph node kind or edge verb without an ADR (#428 must answer this in its ticket).

## 6. Decisions the owner still has to make

1. Accept, edit or defer SPEC-DKB-008 (gates #313).
2. Name the independent reviewer for #437 (gates the C/C++ precision claim).
3. Approve the #427 agent batch after its replay prediction.
4. Whether `feat/workflow-router` (remote leftover) is bundled and deleted, and whether the broken scratch worktrees under `/tmp` and `~/.cache` are cleared.
5. Whether the `sudo du` of the Wazuh directories is worth doing (the root disk was at 99% before the cleanup).

## 7. Out of scope unless the owner asks

Turning on the tool entry point; the workflow router by default; new graph schemas; a full rebuild inside a hook; agent batches that cannot show an effect at n=7.

## 8. First actions in the next session

1. `git switch main && git pull`, then check `gh pr view 444 445` and merge state.
2. `journalctl --user -u devkb-triage -u devkb-nightly --since today` for the first runs from the new paths.
3. Trust the new folder in Claude Code and approve `.mcp.json`.
4. Start with #440 and #436 (they protect everything that follows).
