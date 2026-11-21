# Combine mode: a partial graph answer completed by the original search, in one call

Status: design, nothing built. Evidence: probes and replays dated 2026-11-21, listed in section 2.

## 1. The problem, and what "rejecting" costs

Today a search whose names are not all answered Complete is either left alone (`pass-through`) or given a hint beside it. A
graph answer that *replaces* the search (`substitute`, a denial that carries the answer) is allowed only when every name is
Complete, because an incomplete replacement makes the agent ask again: the denied call, the second call and the tokens of
both are a loss. That rule is why 9% of searches are answered (24 of 256 live; 54 of 381 replayed), and why the replay of
the obvious fix, answer what resolves and drop the rest, only added hints beside grep (+21 answers, none replacing a call).

The way out is not a better rule for when to replace. It is to **never replace**: let the agent's own search run, which is
complete by construction, and combine the graph's part with that result in the same tool call.

## 2. What the platform allows (verified, not assumed)

A documentation summary said `updatedInput` and `updatedToolOutput` exist and were "not confirmed per tool" for Bash and Grep.
Probed on the installed Claude Code (headless, generic prompt, `$0.04` each):

| probe | result |
|---|---|
| PreToolUse on Bash returns `permissionDecision: allow` and `updatedInput.command` | the rewritten command ran (`echo ORIGINAL` became `echo REWRITTEN`); `additionalContext` arrived with it; 2 turns |
| PostToolUse on Bash returns `updatedToolOutput` with `stdout` extended | the model saw the extended output; 2 turns |
| PreToolUse on Grep returns `updatedInput.pattern` | the rewritten pattern ran: asked `alpha_one`, got the `beta_two` line, **with no sign of the change** |
| Grep's PostToolUse `tool_response` shape | `{mode, numFiles, filenames, content, numLines, totalLines}` |

The last row is the hazard: a silent rewrite makes the agent believe its own question was answered. Every rewrite therefore
says what it did. Not documented, so avoided: two hooks returning `updatedInput` or `updatedToolOutput` for one call (the
guardrail's PostToolUse already logs misses: fold both into one script).

## 3. Design

Principles. (1) Never deny. (2) The original search is the source of truth for every name the graph does not cover. (3) One
tool call, one result: what the agent asked, then what the graph adds. (4) Any doubt: return nothing, the call is unchanged.
(5) The addition must cost fewer tokens than it saves, or it is not added.

```
agent: grep -rn "scan_body\|line_end\|outline" devkb/        (3 names; the graph is Complete for one)
  PreToolUse (existing guardrail)   unchanged: passes through, remembers the names
  the search runs                   its full output, as always
  PostToolUse (new)                 reads tool_response; asks the graph about the names; builds the addition;
                                    returns updatedToolOutput = original output + addition
```

The addition, by tier. Each tier has its own gate (section 5); a tier that fails stays off.

| tier | when | addition | saves |
|---|---|---|---|
| T1 span | a name resolves to one definition, Complete | `devkb: scan_body devkb/cpp_symbols.py L583-947 (exact), 7 callers, tests: ...`, and `not in the graph: line_end, outline (the lines above are grep's)` | the agent reads the exact range, not a guess |
| T2 body | one unambiguous definition of at most 60 lines, and the agent asked for it (`def X`) | the body, from the graph's span | the `sed -n a,bp` that follows a locating search |
| T3 compaction (phase 2) | call-site searches whose graph rows equal grep's lines exactly | grep's lines for those names replaced by grouped-by-function rows | tokens only |

Partial answers need no special case: names the graph lacks are covered by the output the original search already produced,
and the addition says which they are. No second search, no denial, no re-ask.

Safeguards. (a) Skip when the call failed, was cut, or its output is empty. (b) A name whose defining file changed since the
graph was built is left out of the addition and listed as "changed since the build: read it" (the name-scoped staleness rule;
under 4% of searches in the replay were affected). (c) Do not repeat an addition for a name already answered in the session
(56 of 256 decisions were repeats). (d) The addition is capped at 600 characters, T2 at 60 lines. (e) Fail open on any
exception and on a hook time of over 5 s (the replay's slowest decision was 2.2 s against the live limit of 20 s).
(f) The rewrite variant (`updatedInput` shrinking the grep to the names the graph does not answer) is phase 2 and needs the
equivalence gate below, because the agent cannot tell a pattern was changed.

## 4. What it is worth, from the data on disk

Measured on the 72 devkb-arm runs: a locating search followed by a ranged read of a file holding a named symbol occurs 39
times; in 18 the range overlaps the symbol's exact span.

| | measured |
|---|---|
| the read covered the whole span | 17 of 18 (one under-read) |
| median lines read against the span | 137 against 36 |
| lines an exact span would not have read | 1497 in 18 reads, about 250 tokens per run |
| calls a body in the answer (T2) would replace | 18 of 72 runs, **0.25 per run, 1.3% of turns** |
| tokens of an addition (replay of the earlier partial mode) | +32 per run |

Estimate: T1 saves about 250 tokens and costs about 32 per run, a net of about 200 once, and more through the later turns that
re-read it (cache reads): roughly 0.3% of a run's context. T2 saves up to 0.25 call per run. **Together under 2% of turns and
well under 1% of cost.** That is below anything a live batch here can detect (a 5% effect needs about 365 runs per arm on turns, 206 on cost, at this batch's spread). The
case for building it is not the size of the gain. It is that it removes the one cost of the guardrail's replacement path, the
re-ask, so the answered share can rise without a penalty, and the two measures to watch are exactness (T1) and avoided calls (T2).

## 5. Gates, in the order they are run

| # | gate | method | pass | cost |
|---|---|---|---|---|
| G1 | exactness | for each recorded locating search, the span the graph gives against the file at the base commit (the text at the start line names the symbol; the end line closes it) | at least 99% exact | free |
| G2 | value | replay the 18 pairs plus the other tickets: lines an exact range spares, and next calls a T2 body makes unnecessary | at least 0.2 calls per run or 200 tokens per run | free |
| G3 | size | the addition's characters per decision, from the replay | median under 150 tokens; net tokens per run at or below 0 | free |
| G4 | equivalence (T3 and the rewrite only) | for each search, graph rows for the resolved names against real grep output on the base tree | 100% of lines kept; none invented | free |
| G5 | pilot | one shuffled batch, `rmain` and `combine` on the same commit, 5 reps, 6 tickets (60 runs, about $24) | pass rate not below `rmain`'s; calls and tokens reported with intervals | paid |
| G6 | confirm | only if G2 predicts 10% or more | 63 runs per arm | paid |

Decision rule: ship a tier when its gates pass and the pilot shows no quality loss; iterate when the sign is right and the size
unproven; kill when G1, G2 or G3 fails. The rewrite variant needs G4 and an explicit note in the output on every use.

## 6. Build order

1. `bench/policy/span_replay.py`: G1-G3 on the recorded runs (extends the measurement above). No product change.
2. PostToolUse addition behind `DEVKB_GUARD_COMBINE=1`, T1 only, with the note and the safeguards; tests with a fixture repository.
3. T2 if G2 holds. 4. The pilot (G5). 5. T3 and the rewrite only after G4.
