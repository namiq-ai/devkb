# Release 0.2.12: performance, dual-mode benchmark, audit and answer intent (2026-11-18)

Questions: is 0.2.12 slower or heavier than 0.2.11? Did devkb help the agents that implemented the release's tickets?
What did an audit of the changes from 0.2.11 to 0.2.12 find? And what does the guardrail actually answer?

## Summary

- **One large performance regression.** prefect (5,542 Python files) builds in 206 s on 0.2.11 and about 450 s on
  0.2.12 (2.2×). The cause is #194: build time grows quadratically with typed-receiver calls. Zephyr builds 17%
  slower. Memory and graph size are flat (+0–6%).
- **No measurable devkb effect on the release's tickets.** With devkb the runs took 5.8 minutes against 6.9 and cost
  $0.64 against $0.65 per run, with the same answer quality. But agents asked devkb nothing themselves in 27 of 28
  runs, and the hook answered 15 searches in 28 runs, so the difference cannot be credited to devkb.
- **The guardrail mostly answers a different question.** Of the 120 answers the 0.2.12 hook gives on 941 recorded
  searches, 34 answer the question the search asked, 34 partly, 52 not (#211, SPEC-DKB-007).
- **The audit filed 31 tickets** (#180–#210, 6 high) and found no wrong answer from devkb in its own 19 queries.

## 1. Performance, 0.2.11 against 0.2.12

### Method

- `bench/perf.py`, as in `performance-v0.2.6-to-v0.2.10.md`: each graph is built three times (wall time, peak memory,
  size on disk), then each command-line query runs five times (median, including interpreter start and graph load).
- Three passes, one after another: 0.2.12, 0.2.11, then 0.2.12 again to measure the noise. Same targets, interpreter
  (Python 3.12) and clones.
- Repositories: click (179 files), mealie (1,781), prefect (5,542), leveldb (154), fmt (148), Zephyr (70,856).
- The first 0.2.12 pass ran while three audit reviewers were also running (load 1.8–2.1); the second ran on a
  quieter machine.
- Raw results, targets, log and script: `bench/results/2026-11-18-perf-v0.2.12/`.

### Noise

The two 0.2.12 passes agree within **4% on build time** for every repository (prefect 452 s and 447 s, Zephyr 162 s
and 164 s), and within 1% on memory and graph size. Every difference below is larger than that.

### Result

| Repository | Build s, 0.2.11 | Build s, 0.2.12 (two passes) | Change | Peak MB, 0.2.11 → 0.2.12 | Graph MB, 0.2.11 → 0.2.12 |
|---|---|---|---|---|---|
| prefect | 205.8 | 452.3 / 447.1 | **+119%** | 589 → 611 | 129.5 → 128.9 |
| Zephyr | 139.2 | 162.1 / 164.1 | **+17%** | 1,664 → 1,764 | 421.3 → 440.0 |
| click | 14.0 | 15.5 / 16.0 | +11% | 60 → 59 | 6.4 → 6.5 |
| leveldb | 1.19 | 1.28 / 1.29 | +8% | 43 → 43 | 3.9 → 4.0 |
| mealie | 73.7 | 75.9 / 79.1 | +3–7% | 161 → 164 | 26.2 → 26.6 |
| fmt | 2.24 | 2.27 / 2.26 | 0% | 52 → 55 | 5.7 → 6.0 |

**Queries.** Most medians are within ±10% of 0.2.11. On Zephyr, `symbol` went from 2.8 s to 3.6–4.5 s, `uses` from
3.7 s to 4.5–5.7 s and `outline` from 1.8 s to 2.4–2.6 s. The other repositories answer every query in 0.15–0.65 s on
both versions, except `query about` on prefect (about 2.3–2.5 s on both).

**Cause of the prefect regression.** On an idle machine, the audit's synthetic repositories reproduce two quadratic
builds introduced in 0.2.12:

| Case | 0.2.11 | 0.2.12 |
|---|---|---|
| typed-receiver calls, 100 / 200 / 400 files | 1.62 / 3.16 / 6.30 s | 5.98 / 22.25 / 80.73 s (#194) |
| module constants in one file, 5,000 / 10,000 / 20,000 | 0.25 / 0.45 / 0.87 s | 0.95 / 3.33 / 11.35 s (#195) |

Peak memory is flat while time doubles, so the time goes to scanning, as #194 describes.

## 2. Dual-mode benchmark over the release's tickets

### Method

- Each ticket of 0.2.12 implemented by Sonnet agents from the issue as filed, in two arms: **no devkb** (devkb's files
  kept, devkb denied, no graph) and **devkb CLI** (graph built, devkb through the shell, the repository's guardrail
  hook). 2 runs per arm per ticket; #131 had 4. #117 compared the older enforcing hook (`cli130`) with no devkb.
- Scored by the full test suite and by a hidden check per ticket, which is never shown to the agent.
- Per-ticket table: `bench/results/2026-11-18-release-0.2.12/dual-mode-per-ticket.md`.

### Result

| Arm | Runs | Wall | Turns | Grep | devkb queries by the agent | Searches the hook replaced | Context tokens | Cost per run (total) | Hidden check | Suite green |
|---|---|---|---|---|---|---|---|---|---|---|
| no devkb | 28 | 6.9 min | 37.7 | 11.6 | — | — | 1,930k | $0.65 ($18.28) | 15/28 | 23/28 |
| devkb CLI | 28 | 5.8 min | 37.3 | 10.4 | 0.3 | 0.1 | 1,903k | $0.64 ($17.92) | 14/28 | 28/28 |

What these numbers can and cannot say:
- **devkb was barely used.** The agents ran devkb queries themselves in 1 of 28 runs (8 queries, in a #117 run). The
  hook replaced 3 searches and added an answer beside 12.
- **The differences are within the noise.** With 2 runs per arm, single tickets swung by 20–37% in either direction,
  and the largest savings came on tickets where devkb gave no answer at all (#135 −37%, #151 −20%, #166 −18%). The
  tickets where devkb answered most cost slightly more (#143 +6%, #162 +6%).
- **Quality was the same.** Hidden-check cases passed: 105/125 without devkb, 98/121 with it. Where the arms differ
  (#131, #150), devkb gave no answer in those runs. Both arms failed the same cases on #166 and #143: the hard parts of
  those tickets. #166's failing case is exactly the defect later filed as #180, which shipped.
- **The red suites without devkb are mostly setup.** 4 of the 5 come from #114 and #117, whose no-devkb checkout
  deletes `AGENTS.md`, `.claude/` and the guardrail's scripts and tests. The failure counts are identical across runs
  (10 and 10, 17 and 17), and a fresh checkout of that arm fails before an agent starts. Excluding them: 23/24 against
  28/28.

**For the next release:** at least 3 runs per arm, and a no-devkb checkout whose suite starts green.

## 3. What the guardrail answers

To see why devkb did not help, the 941 code searches of these runs were replayed through the 0.2.12 hook (main at
`268edf8`). 120 get a devkb answer. Each was labelled with what the command that triggered it asked, by rules and then
by hand. The labels and the script are in `bench/results/2026-11-18-release-0.2.12/`.

| The search asks | Answers | devkb gave | Verdict |
|---|---|---|---|
| a body (`grep -n "def X" -A40`) | 38 | callers of X | different question |
| a body | 13 | location and body | same |
| call sites, repository-wide | 18 | callers of X | same |
| call sites, filtered by a pipe | 14 | all callers | partly |
| lines in one file | 11 | callers across the repository | partly |
| where X is defined | 12 | a "Defined at" line in a callers pack (9), location and body (3) | partly / same |
| the functions in a file (`grep -n "^def "`) | 10 | callers of `Def`, or of another file's `pack` | different question |
| literal text, a count | 4 | a pack | different question |

**34 of 120 answer the question asked, 34 partly, 52 not.** The answers are also large: 64% of a pack's text is fixed
wording, and in #143 the one right-question answer was 4× the size of grep's output.

The cause is in the design, not one bug. Since #131 the hook asks one graph question, the direct-caller pack, for
every name it finds in a pattern. SPEC-DKB-005 (#162) decided only whether that answer *replaces* the search or goes
*beside* it, and treated "beside" as the safe outcome. #211 files this as one problem. SPEC-DKB-007 maps each intent to
its own graph question and answer shape, and adds a direct path where an agent asks the graph by intent. Its stories
are #214–#218.

## 4. Audit of 0.2.11 → 0.2.12

Three reviewers covered the guardrail, the graph and read tools, and the triage and benchmark code, using devkb. Every
finding was reproduced twice.

| Area | Tickets | High | Medium | Low |
|---|---|---|---|---|
| Guardrail | #180–#191 | 3 | 4 | 5 |
| Graph and query tools | #192–#204 | 3 | 4 | 6 |
| Triage reliability and benchmark code | #205–#210 | 0 | 3 | 3 |

High: #180 (context options mask `-v`/`-c`/`-l`), #181 (`--include`, glob and type ignored), #182 (a stale graph still
replaces grep), #192 (a call through a package re-export is dropped while the pack says Complete), #193 (a dataclass
field named like a function hides its callers), #194 (quadratic build).

**devkb in the audit:** 19 queries by the reviewers, 15 right, 3 partly right (callers through re-exports, #192), 1
unused, none wrong.

**What the audit did not find, and why.** It did not flag #211, though 52 of 120 answers are to a different question.
The guardrail reviewer checked each behaviour against the specification that defined it: SPEC-DKB-005 for
replacement, SPEC-DKB-006 for the definition answer. 6 of its 12 findings are searches **denied** with a wrong answer,
and for three of them the expected result it wrote was "alongside" or "passes through", because SPEC-DKB-005 defines an answer beside
grep as the safe outcome. An answer to the wrong question *beside* the search breaks no requirement, so a
conformance audit cannot see it. It also tested synthetic fixtures, one rule at a time, not the searches agents
actually made. Two changes follow:
- an audit of the guardrail replays recorded agent searches and judges each answer against what the search asked, not
  only against the spec's decision table;
- SPEC-DKB-007 makes the answer's question a requirement (R1, R2, R8), so the next audit can check it.

## 5. Corrections to earlier figures

- The benchmark's `guardrail_fired` count includes the hook's pass-throughs (#209). The dual-mode tables above use their
  own counter, so their replaced-search column is not affected.
- The listing-then-read share behind dropping C3 (#168) is 31%, not 30% (#210). The decision stands.
- **The devkb arm was not purely "devkb as on main"** (#225). Its own `devkb` command and its graph builds came from a
  tool environment built for #126, while the hook came from the checkout. And every run also loaded the machine's
  user-level settings, so two guardrail copies ran, and whichever answered first won. The 0.2.13 benchmark builds each
  arm's devkb from an exact commit and records it, and loads only the checkout's settings.
- **Hidden checks were readable.** For #114–#132 the agent's checkout contained `bench/policy/accept/`, its own hidden
  check included (#223). Nothing shows an agent opened one, but those tickets' quality figures are not blind.
- The `def` noise in alongside answers is not fixed in 0.2.12 for keyword-only patterns: `grep -n "^def " FILE` is
  still answered for `class Def`, because the resolver's exact tier ignores case (#211, #215).

## 6. What to do first

1. #194, then #195: the build regressions, largest on big Python repositories.
2. #214–#216: classify each search's intent and answer it with the question it asks. Until then, the owner's user-level
   hook runs with substitution off.
3. #180–#182: the high guardrail defects, which #216 also keeps as regression tests.
4. The benchmark: 3 runs per arm and a no-devkb checkout whose suite starts green, before the next release table.
