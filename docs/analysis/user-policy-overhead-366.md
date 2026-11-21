# What offering devkb costs a user's repository (#366)

The benchmark's devkb arm (`main`) runs in this repository, whose `AGENTS.md` also carries the process for developing
devkb itself ("Developing devkb: devkb first, logged"). No user repository has that text, so the 0.2.14 figure of
+3.3k to +4.0k tokens on the first call was not what a user pays. This note measures it.

## Arms

The same prompt, suite and permissions in every arm; the devkb arms run main's devkb (pinned to the ticket's base),
`none` none at all. They differ in the policy files, the MCP server, the guardrail hook and what devkb gives up front.

| Arm | AGENTS.md / CLAUDE.md | MCP server | Guardrail hook | Up front |
|---|---|---|---|---|
| `none` | removed; devkb denied | no | no | nothing |
| `userinit` | exactly what a default `devkb init` writes (`AGENTS_BLOCK`, 3,986 characters; `CLAUDE.md` = `@AGENTS.md`) | devkb's, as init registers it (`--toolset lean-pack`, 12 tools) | no (init installs none) | nothing |
| `userpolicy` | the same files | no | this repository's guardrail | nothing |
| `short` | the same, with the block cut to the commands agents act on (`SHORT_BLOCK`, 787 characters) | no | the guardrail | nothing |
| `inject` | as `userpolicy` | no | the guardrail | `devkb pack file` of the first code file "Where to start" names, in front of the prompt |
| `outline` | this repository's own files | no | the guardrail, plus a file's outline on its first Read | nothing |
| `main` | this repository's own files (the user block plus the developer section) | no | the guardrail | nothing |

`userinit` is what a user's repository gets from `devkb init` today. `userpolicy` and `short` isolate the policy text
(the ticket's item 1 and the `short` candidate), with the hook the benchmark uses. First-call context is the first model
call's input, cache-read and cache-creation tokens. Two tickets that need no navigation (#383 at 2e216fc; #303 at
4b656e1), 3 runs per arm and ticket, one shuffled batch per ticket: 42 runs, with the harness at adfc547 (before the
merge of #397, whose command paragraph now lengthens every arm's prompt alike).

## Results (batch 2)

Made by `python bench/policy/arm_table.py bench/results/2026-11-20-user-policy-366/batch2-rows.jsonl`. Turns are the scored
rows' turns (model calls), as in batch 1.

#383

| Arm | n | First-call context k | Over none | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | Cache written k (mean) | Suite | Hidden check | devkb queries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 3 | 17.8 | 0 | 9 | 214 | $0.097 | +0% | 9 | 3/3 | 0/3 | 0 |
| userpolicy | 3 | 19.4 | +1.6k | 9 | 218 | $0.109 | +12% | 11 | 3/3 | 0/3 | 0 |
| userinit | 3 | 20.3 | +2.5k | 8 | 199 | $0.148 | +52% | 25 | 3/3 | 0/3 | 0 |
| short | 3 | 18.3 | +0.4k | 12 | 272 | $0.117 | +21% | 13 | 3/3 | 0/3 | 0 |
| outline | 3 | 21.9 | +4.1k | 10 | 269 | $0.107 | +10% | 13 | 3/3 | 0/3 | 0 |
| inject | 3 | 19.9 | +2.1k | 10 | 254 | $0.124 | +28% | 17 | 3/3 | 0/3 | 0 |
| main | 3 | 21.9 | +4.1k | 9 | 229 | $0.112 | +16% | 16 | 3/3 | 0/3 | 0 |

#303

| Arm | n | First-call context k | Over none | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | Cache written k (mean) | Suite | Hidden check | devkb queries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 3 | 17.7 | 0 | 8 | 200 | $0.124 | +0% | 13 | 3/3 | 3/3 | 0 |
| userpolicy | 3 | 19.3 | +1.6k | 10 | 275 | $0.138 | +12% | 15 | 3/3 | 3/3 | 0 |
| userinit | 3 | 20.2 | +2.5k | 10 | 286 | $0.166 | +34% | 20 | 3/3 | 3/3 | 0 |
| short | 3 | 18.1 | +0.5k | 10 | 264 | $0.136 | +10% | 15 | 3/3 | 3/3 | 0 |
| outline | 3 | 21.0 | +3.3k | 9 | 259 | $0.141 | +14% | 15 | 3/3 | 3/3 | 0 |
| inject | 3 | 20.1 | +2.4k | 10 | 275 | $0.132 | +6% | 12 | 3/3 | 3/3 | 0 |
| main | 3 | 21.0 | +3.3k | 11 | 320 | $0.169 | +36% | 22 | 3/3 | 3/3 | 0 |

Pooled (cost vs none: the mean of the tickets' ratios)

| Arm | n | First-call context k | Over none | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | Cache written k (mean) | Suite | Hidden check | devkb queries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 6 | 17.7-17.8 | 0 | 8 | 207 | $0.110 | +0% | 11 | 6/6 | 3/6 | 0 |
| userpolicy | 6 | 19.3-19.4 | +1.6k | 10 | 275 | $0.124 | +12% | 13 | 6/6 | 3/6 | 0 |
| userinit | 6 | 20.2-20.3 | +2.5k | 10 | 251 | $0.157 | +43% | 23 | 6/6 | 3/6 | 0 |
| short | 6 | 18.1-18.3 | +0.4 to +0.5k | 10 | 265 | $0.127 | +15% | 14 | 6/6 | 3/6 | 0 |
| outline | 6 | 21.0-21.9 | +3.3 to +4.1k | 10 | 264 | $0.124 | +12% | 14 | 6/6 | 3/6 | 0 |
| inject | 6 | 19.9-20.1 | +2.1 to +2.4k | 10 | 264 | $0.128 | +17% | 14 | 6/6 | 3/6 | 0 |
| main | 6 | 21.0-21.9 | +3.3 to +4.1k | 10 | 244 | $0.141 | +26% | 19 | 6/6 | 3/6 | 0 |


**First call** (constant per arm and base):
- **what `devkb init` gives a user today (`userinit`): +2.5k tokens** over `none` (20.2-20.3k against 17.7-17.8k):
  1.6k of it the policy files (`userpolicy` minus `none`) and 0.9k devkb's MCP server (12 tools and 3 MCP resource
  tools: `userinit` minus `userpolicy`);
- the block alone (`userpolicy`): +1.6k; with the short block (`short`): +0.4-0.5k;
- this repository's own files (`main`, `outline`, the earlier "+3.3k"): +3.3k to +4.1k;
- `inject`: +2.1-2.4k (the pack of `devkb/cli.py` on #383, of `bench/policy/storybench.py` on #303).

**Per run:** 3 runs per cell show only effects above about 40% (#368), and costs moved ±25% between the two batches for
the same arm and ticket. `userinit` costs the most on both tickets (+52% and +34% against `none`, +43% pooled), but mostly
because of the prompt cache, not its 0.9k of tool definitions: its tool list was a prefix no earlier run had cached, so
its runs wrote 24.8k cache tokens each on #383 against 9.3k for `none` (20.4k against 13.0k on #303), while `none` read its first
call wholly from cache (warmed by batch 1). Per-run cost in these batches ranks arms partly by how warm the cache was;
a warm-up call per arm before a batch, or pricing cache reads and writes apart, would remove that. The other arms'
differences (+10% to +36%) are within the noise. Correctness was the same in every arm (#383: 0/3 everywhere, its strict hidden check; #303: 3/3
everywhere), and no agent ran a devkb query or called an MCP tool.

**Batch 1** (36 runs, six arms, no `userinit`) is superseded: its `inject` arm packed the longest file path in the
ticket, not the file "Where to start" names (`devkb/build_symbols.py` instead of `devkb/cli.py` on #383; found in
review). Its first-call figures for the other arms are the same as here.

## Against the proposed target

#366 proposed: the shipped configuration adds at most 1.0k tokens to the first call and costs at most +5% per run
against `none` on tickets that need no navigation (owner to confirm).

- **First call:** what ships (`userinit`) adds 2.5k, more than twice the target; without the MCP server it is 1.6k;
  only the short block, without the MCP server, meets it (0.4-0.5k).
- **Per run:** `userinit` is +43% here; whether any arm is within +5% cannot be told from 3 runs per cell.

**What follows (owner's decision):** the larger part of what a user pays on the first call is the policy text (1.6k),
then the MCP server (0.9k); the short block saves 1.1-1.2k of the text. Neither change is measured on tickets where navigation
matters: whether agents still use devkb with the short block, or without MCP, needs a navigation ticket under the
repetition rule before `devkb init`'s defaults change. `devkb/init.py` is not changed here.

## Data

`bench/results/2026-11-20-user-policy-366/batch2-rows.jsonl` (each run's scored row, plus its first-call tokens, its
MCP servers, its cache reads and writes and the harness commit) and `batch1-results-*.jsonl` (batch 1).
Streams of both batches: `devkb-benchmark-366-user-policy-archive.tar.gz` and `-batch2.tar.gz`, beside the checkout.
