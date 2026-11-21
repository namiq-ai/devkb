# What offering devkb costs a user's repository (#366)

The benchmark's devkb arm (`main`) runs in this repository, whose `AGENTS.md` also carries the process for developing
devkb itself ("Developing devkb: devkb first, logged"). No user repository has that text, so the 0.2.14 figure of
+3.3k to +4.0k tokens on the first call was not what a user pays. This note measures it.

## Arms

All arms run main's devkb (pinned to the ticket's base), the same prompt, the same suite and the same permissions;
they differ only in the policy files and in what devkb gives up front.

| Arm | AGENTS.md / CLAUDE.md | Up front |
|---|---|---|
| `none` | removed, with the guardrail; devkb denied | nothing |
| `userpolicy` | exactly what `devkb init` writes: the `AGENTS_BLOCK` of the arm's devkb (3,986 characters), `CLAUDE.md` = `@AGENTS.md` | the guardrail |
| `short` | the same, with the block cut to the commands agents act on (`SHORT_BLOCK`, 787 characters) | the guardrail |
| `outline` | this repository's own files | the guardrail, plus a file's outline on its first Read |
| `inject` | as `userpolicy` | the guardrail, plus `devkb pack file` of the ticket's code file in front of the prompt |
| `main` | this repository's own files (the user block plus the developer section) | the guardrail |

First-call context is the first model call's input, cache-read and cache-creation tokens. Two tickets that need no
navigation (#383 at 2e216fc, a one-line fix; #303 at 4b656e1), 3 runs per arm and ticket, one shuffled batch per
ticket: 36 runs.

## Results


#383
| Arm | n | First-call context k (min-max) | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | Suite | Hidden check | devkb log entries |
|---|---|---|---|---|---|---|---|---|---|
| none | 3 | 17.8-17.8 | 9 | 216 | $0.132 | +0% | 3/3 | 0/3 | 0 |
| userpolicy | 3 | 19.4-19.4 | 9 | 229 | $0.147 | +12% | 3/3 | 0/3 | 0 |
| short | 3 | 18.3-18.3 | 7 | 154 | $0.100 | -24% | 3/3 | 0/3 | 0 |
| outline | 3 | 21.9-21.9 | 9 | 238 | $0.124 | -5% | 3/3 | 0/3 | 0 |
| inject | 3 | 24.3-24.3 | 12 | 370 | $0.194 | +47% | 3/3 | 0/3 | 3 |
| main | 3 | 21.9-21.9 | 8 | 201 | $0.116 | -12% | 3/3 | 0/3 | 0 |

#303
| Arm | n | First-call context k (min-max) | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | Suite | Hidden check | devkb log entries |
|---|---|---|---|---|---|---|---|---|---|
| none | 3 | 17.7-17.7 | 8 | 205 | $0.153 | +0% | 3/3 | 3/3 | 0 |
| userpolicy | 3 | 19.3-19.3 | 11 | 317 | $0.167 | +9% | 3/3 | 3/3 | 0 |
| short | 3 | 18.1-18.1 | 9 | 221 | $0.134 | -12% | 3/3 | 3/3 | 0 |
| outline | 3 | 21.0-21.0 | 13 | 372 | $0.182 | +19% | 3/3 | 3/3 | 0 |
| inject | 3 | 20.1-20.1 | 9 | 236 | $0.144 | -6% | 3/3 | 3/3 | 3 |
| main | 3 | 21.0-21.0 | 9 | 263 | $0.157 | +3% | 3/3 | 3/3 | 0 |

Pooled (cost vs none = mean of the two tickets' ratios)
| Arm | n | First-call context k (min-max) | Turns (med) | Context k (med) | Cost (mean) | Cost vs none (mean ratio) | Suite | Hidden check | devkb log entries |
|---|---|---|---|---|---|---|---|---|---|
| none | 6 | 17.7-17.8 | 8 | 211 | $0.142 | +0% | 6/6 | 3/6 | 0 |
| userpolicy | 6 | 19.3-19.4 | 10 | 280 | $0.157 | +10% | 6/6 | 3/6 | 0 |
| short | 6 | 18.1-18.3 | 8 | 187 | $0.117 | -18% | 6/6 | 3/6 | 0 |
| outline | 6 | 21.0-21.9 | 10 | 266 | $0.153 | +7% | 6/6 | 3/6 | 0 |
| inject | 6 | 20.1-24.3 | 10 | 285 | $0.169 | +21% | 6/6 | 3/6 | 6 |
| main | 6 | 21.0-21.9 | 9 | 256 | $0.136 | -5% | 6/6 | 3/6 | 0 |

**First call** (constant per arm and base; the measured overhead of offering devkb):
- what a user's repository pays with `devkb init` today (`userpolicy`): **+1.6k tokens** over `none` (19.3-19.4k
  against 17.7-17.8k); the block's text accounts for about 1.15k of it (the difference to `short`, whose files are the
  same apart from the block), and the other 0.45k is paid by `short` too (not broken down here);
- with the short block: **+0.4-0.5k**;
- this repository's own files (`main`, the earlier "+3.3k"): +3.3k to +4.1k, of which about 1.7-2.5k is the developer
  section no user carries;
- `inject`: +2.4k on #303 and +6.6k on #383 (the pack of `devkb/build_symbols.py` is 12k characters).

**Per run:** with 3 runs per cell, cost moves ±25% between arms on the same ticket (`short` -24% and `main` -12% on
#383, `outline` +19% on #303), in both directions and unrelated to the first-call order, so these runs cannot rank the
arms by cost (#368: 3 runs show only effects above about 40%). `inject` was the most expensive on #383 (+47%, 12 turns
against 9), where the injected pack was largest. The hidden check gave the same result in every arm (#383: 0/3
everywhere, its stricter check; #303: 3/3 everywhere); no agent ran a devkb query.

## Against the proposed target

#366 proposed: the shipped configuration adds at most 1.0k tokens to the first call and costs at most +5% per run
against `none` on tickets that need no navigation (owner to confirm).

- **First call:** `userpolicy` (what ships) does not meet it (+1.6k); `short` does (+0.4-0.5k).
- **Per run:** not decidable from these runs; a check of +5% needs far more than 3 runs per cell (#368).

**Recommendation (owner's decision):** ship the short block as `devkb init`'s `AGENTS_BLOCK` (it keeps the four
commands and the "Complete is the whole answer" rule; it drops the table and the MCP names), and measure the per-run
cost under the repetition rule before calling the target met. `inject` is not a candidate on this evidence: it costs
the most context and changed nothing the agents did.

## Data

`bench/results/2026-11-20-user-policy-366/results-383.jsonl` and `results-303.jsonl` (one row per run; `first_ctx`,
`cost`, `turns`, `ctx_tokens`, the hidden check and the suite). Streams: `devkb-benchmark-366-user-policy-archive.tar.gz`,
beside the checkout.
