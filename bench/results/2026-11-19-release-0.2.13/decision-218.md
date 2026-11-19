**Decision on the two direct-path candidates (SPEC-DKB-007 S5, D1 and D2): D1 is kept, D2 is dropped.**

The rule from this ticket: a candidate is kept when agents query devkb directly more often and cost does not rise.

**Benchmark:** the last 0.2.13 batch. Main fe036c2, Sonnet, 6 tickets (#203, #118, #120, #205–#208, #137/#138, #175), 3 runs per ticket and arm, 18 runs per arm.
- Hook only is the `main` arm; hook + D1 is `teach` (`DEVKB_GUARDRAIL_TEACH=1`); hook + D2 is `outline` (`DEVKB_GUARDRAIL_OUTLINE=1`).
- Counts are recounted from the transcripts with the corrected rules of #258: turns are model calls, output tokens come from the session totals, and a devkb query before the run's first edit of devkb's code is navigation.
- Two runs that never reached the model were rerun. Red suites were re-run with the #260 rule; none was flaky.

| Arm | devkb navigation queries a run | Runs with any | Cost vs hook only | Context | Turns | grep calls | Hidden check | Suite |
|---|---|---|---|---|---|---|---|---|
| hook only (main) | 0.17 | 3 of 18 | — | — | — | — | 14/18 | 18/18 |
| **hook + D1 (teach)** | **1.50** | **9 of 18** | **−11%** | **−15%** | **−10%** | +1% | 15/18 | 18/18 |
| hook + D2 (outline) | 0.47 | 4 of 17 | +1% | +3% | +1% | +18% | 14/18 | 16/18 |

- The cost, context, turns and grep ratios are geometric means of the per-ticket ratios to hook only. Each ticket's difference alone is within noise. D1 costs less than hook only on 4 of 6 tickets (#203, #118, #120, #137) and more on 2 (#205, #175).
- The no-devkb and v0.2.12 arms make 0.28 navigation queries a run. There, agents run the repository's own devkb, the tool they are editing.
- #137's hidden check fails on every arm, for a gap in the agents' fixes, not in the hook. It counts the same against every arm.

**D1, kept.** Direct navigation queries rise about 9-fold, and in half the runs. Agents run the command the answer names (`.venv/bin/devkb outline …`, `devkb pack --project . file …`). Cost, context and turns fall, with no loss of quality.

**D2, dropped.** It barely changes direct use (0.47 against 0.17). It adds grep calls (+18%) and does not lower cost. Two of its suites were red, against none for D1. The outline on first open overlaps the hook's own list-symbols answer, and agents keep searching after receiving it.

**The 20-answer hand-check:** 20 saved answers (`DEVKB_GUARDRAIL_KEEP`), across every answer kind and arm. The list is in `analysis/handcheck-218.json` in the bench data.
- **20 of 20 answer the question the search's intent names:**
  - locate: location lines;
  - read-body: the body, or a span note when the body runs past 80 lines;
  - list-symbols: the outline.
- **1 may be partial.** A definition search for three names (`answer_or_record`, `changed_since_build`, `graph_state`) got one location; the other two are defined in another file, possibly outside the search's scope.
- **Size:** 89 to 1,641 characters, under the 1,500-character budget except two read-body answers that carry a whole body (1,606 and 1,641).

**The release table's answer columns** come from the saved answers for every devkb run (`Hook answers (chars)`).

**What follows:** D1 is still off by default. Turning it on, and removing D2's setting, is a change to the hook's behaviour, so it needs its own ticket.
