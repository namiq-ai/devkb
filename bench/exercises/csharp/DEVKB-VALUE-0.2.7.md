# devkb 0.2.7 on C#: the same chain questions, scored against the compiler

Same six questions, same pinned repositories and the same Roslyn truth as the 0.2.6 report (`DEVKB-VALUE.md`); the
plain arm's 12 runs are reused from it (the plain agent does not depend on devkb's version). The devkb arm ran on
**devkb 0.2.7 installed from PyPI** (`uv tool install "devkb[mcp]==0.2.7"`; its C# extractor is byte-identical to the
benchmarked branch). Sonnet, 2 runs per question per arm. Transcripts: `runs-0.2.7/`, `runs-0.2.7-noread/`.

0.2.7 changes two things at once against 0.2.6: the C# graph (round 4, #40) and the default `lean-pack` toolset, which
now also carries the read tools (`symbol`, `outline`, `uses`, `search_docs`; #39). The second arm separates them: the
0.2.7 graph with the read tools denied (`DEVKB_DENY=uses,outline,symbol,search_docs bench/cs_value.py run`), which is
0.2.6's toolset.

## Summary

**Correction (after #47).** The first version of this report said criterion 6 was not met (precision 0.82). That was
the benchmark's truth, not the agent: the compiler truth records calls only, and EF Core's target is reached through
four properties, so 29 methods that do reach it were scored wrong (`truth-corrections.md`, each path read in the
source). Scored with those corrections, kept beside the compiler truth in `questions.json`
(`python bench/cs_value_rescore.py bench/exercises/csharp/questions.json bench/exercises/csharp/runs ...`):

| All 12 runs | Precision, compiler truth (as first published) | Precision, corrected | Recall, corrected | Test files | Turns | Median cost vs plain |
|---|---|---|---|---|---|---|
| plain agent (reused) | 0.60 | 0.73 | 0.95 | 0.56 | 12.7 | $0.207 |
| 0.2.6 (`DEVKB-VALUE.md`) | 0.85 | 0.97 | 0.89 | 0.66 | 7.6 | −40% |
| **0.2.7, default tools** | 0.82 | **0.98** | **0.94** | 0.75 | 8.8 | **−53%** |
| 0.2.7, read tools denied | 0.80 | 0.91 | 0.88 | 0.77 | 8.7 | −42% |

Per question, devkb-arm precision, corrected (compiler truth alone in brackets):

| Question | Truth | 0.2.6 | 0.2.7 | 0.2.7, read tools denied |
|---|---|---|---|---|
| MediatR `ServiceRegistrar.GetConcreteRequestTypes` | 5 | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) |
| FluentValidation `ValidationContext.GetFromNonGenericContext` | 9 | 0.88 (0.88) | 0.90 (0.90) | 0.86 (0.86) |
| Polly `ComponentDisposeHelper.ThrowDisposed` | 10 | 1.00 (0.89) | 1.00 (0.88) | 0.78 (0.72) |
| Polly `CircuitStateController.EnsureNotDisposed` | 9 | 1.00 (0.91) | 1.00 (0.86) | 0.90 (0.69) |
| Jellyfin `DynamicHlsHelper.GetOutputVideoCodecProfile` | 10 | 1.00 (1.00) | 1.00 (1.00) | 0.95 (0.95) |
| EF Core `ModificationCommand.GetTableMapping` | 9 + 29 | 0.93 (0.45) | 0.96 (0.25) | 0.94 (0.59) |

## What this shows, and what it does not

- **Criterion 6 of #40 is met** with the corrected truth: precision 0.98 (≥ 0.85), recall 0.94 against the larger
  truth (0.96 against the compiler's; the criterion was written for it). Against the compiler truth alone it reads 0.82,
  and that number measured the truth's gap, not the agent.
- **What the first version took for a drop.** EF Core's answers come in two sizes: 14–17 names or 33–39. The compiler
  truth punished the long ones (0.23–0.27) because most of their names reach the target through `ColumnModifications`.
  0.2.6 drew one of each, 0.2.7 two long ones. Corrected, the long answers are the best: 0.2.7 found 38 and 30 of the
  38 known callers at precision 0.97 and 0.94 (the `SaveChanges` entry points among them), 0.2.6's long run 32 at 0.94;
  the short ones found 12–15 at 0.88–1.00.
- **The read tools help.** Denied, precision is 0.91 and recall 0.88, both below the default arm; most of the
  difference is the Polly runs without them naming dispose methods that do not reach the target.
- **Where the C# round reached these questions.** The first pack answer, compared run by run with 0.2.6's: on
  FluentValidation it now resolves 12 symbols where 0.2.6 resolved 1 (`ValidationContext<T>.GetFromNonGenericContext`
  is a static call on a generic type, round 4's F6, the miss that motivated it); on MediatR, Polly `EnsureNotDisposed`,
  Jellyfin and EF Core it is identical; in both Polly `ThrowDisposed` runs the agent asked `callers` instead.
- **Limits.** The corrections cover names agents listed; the full set of EF Core callers through those properties may
  be larger, so corrected recall is an upper bound. Two names stay unproven and are counted wrong. The lasting fix is
  in the truth tool (`truth-corrections.md`, last section), not yet run. 2 runs per question.
- Two devkb limitations the runs exposed are in `docs/specs/csharp-4-dogfood-log.md` (D8: EF Core's fixture copies
  under `eng/**/fixtures/` make `callers CommandBatchPreparer.BatchCommands` ambiguous; D9: the EF Core exploration,
  which turned out to find the real callers).

## Result, 0.2.7 with the default tools (compiler truth alone, as first published)

| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Cost | Grep | File load | devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MediatR `ServiceRegistrar.GetConcreteRequestTypes` | plain | 5 | 8 | 0.67 | 1.00 | 0.12 | 9.5 | 7.5 | $0.115 | 6.5 (9.6k) | 2.0 (16.4k) | 0 |
|  | devkb | 5 | 5 | 1.00 | 1.00 | 1.00 | 3.5 | 3.5 | $0.070 | 0.5 (0.0k) | 0 | 1.0 (8.1k) |
| FluentValidation `ValidationContext.GetFromNonGenericContext` | plain | 9 | 18 | 0.73 | 1.00 | 0.95 | 11.5 | 10.5 | $0.227 | 9.0 (36.1k) | 0.5 (0.5k) | 0 |
|  | devkb | 9 | 10 | 0.90 | 1.00 | 0.90 | 8.0 | 8.0 | $0.125 | 4.0 (9.3k) | 0 | 1.0 (5.7k) |
| Polly `ComponentDisposeHelper.ThrowDisposed` | plain | 10 | 12 | 0.76 | 0.90 | 0.16 | 19.5 | 12.0 | $0.248 | 13.0 (41.3k) | 5.5 (6.4k) | 0 |
|  | devkb | 10 | 8 | 0.88 | 0.75 | 0.11 | 10.0 | 6.0 | $0.114 | 6.0 (13.1k) | 1.0 (1.6k) | 1.0 (0.7k) |
| Polly `CircuitStateController.EnsureNotDisposed` | plain | 9 | 20 | 0.61 | 1.00 | 1.00 | 11.0 | 8.5 | $0.195 | 7.5 (27.8k) | 2.5 (18.6k) | 0 |
|  | devkb | 9 | 10 | 0.86 | 1.00 | 1.00 | 6.0 | 5.5 | $0.078 | 3.0 (3.8k) | 0 | 1.0 (3.9k) |
| jellyfin `DynamicHlsHelper.GetOutputVideoCodecProfile` | plain | 10 | 14 | 0.64 | 0.90 |  | 9.5 | 6.5 | $0.111 | 7.5 (16.0k) | 1.0 (2.1k) | 0 |
|  | devkb | 10 | 10 | 1.00 | 1.00 |  | 3.0 | 3.0 | $0.047 | 0 | 0 | 1.0 (3.5k) |
| efcore `ModificationCommand.GetTableMapping` | plain | 9 | 43 | 0.17 | 0.83 |  | 15.0 | 10.5 | $0.386 | 12.5 (88.9k) | 1.0 (27.6k) | 0 |
|  | devkb | 9 | 36 | 0.25 | 1.00 |  | 22.5 | 12.5 | $0.245 | 8.0 (30.1k) | 1.5 (6.4k) | 10.0 (14.6k) |
| **All 12 runs** | **plain** |  |  | 0.60 | 0.94 | 0.56 | 12.7 | 9.2 | $0.214 | 9.3 (36.6k) | 2.1 (11.9k) | 0 |
| **All 12 runs** | **devkb** |  |  | 0.82 | 0.96 | 0.75 | 8.8 | 6.4 | $0.113 | 3.6 (9.4k) | 0.4 (1.3k) | 2.5 (6.1k) |

## Result, 0.2.7 with the read tools denied (compiler truth alone)

| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Cost | Grep | File load | devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MediatR `ServiceRegistrar.GetConcreteRequestTypes` | plain | 5 | 8 | 0.67 | 1.00 | 0.12 | 9.5 | 7.5 | $0.115 | 6.5 (9.6k) | 2.0 (16.4k) | 0 |
|  | devkb | 5 | 5 | 1.00 | 1.00 | 1.00 | 3.5 | 3.5 | $0.071 | 0 | 0 | 1.5 (8.3k) |
| FluentValidation `ValidationContext.GetFromNonGenericContext` | plain | 9 | 18 | 0.73 | 1.00 | 0.95 | 11.5 | 10.5 | $0.227 | 9.0 (36.1k) | 0.5 (0.5k) | 0 |
|  | devkb | 9 | 13 | 0.86 | 1.00 | 0.95 | 9.0 | 9.0 | $0.141 | 6.0 (16.7k) | 0 | 1.0 (5.7k) |
| Polly `ComponentDisposeHelper.ThrowDisposed` | plain | 10 | 12 | 0.76 | 0.90 | 0.16 | 19.5 | 12.0 | $0.248 | 13.0 (41.3k) | 5.5 (6.4k) | 0 |
|  | devkb | 10 | 12 | 0.72 | 0.90 | 0.13 | 11.5 | 8.0 | $0.155 | 7.5 (20.3k) | 2.5 (3.2k) | 0 |
| Polly `CircuitStateController.EnsureNotDisposed` | plain | 9 | 20 | 0.61 | 1.00 | 1.00 | 11.0 | 8.5 | $0.195 | 7.5 (27.8k) | 2.5 (18.6k) | 0 |
|  | devkb | 9 | 13 | 0.69 | 1.00 | 1.00 | 10.5 | 6.0 | $0.128 | 5.0 (8.1k) | 2.5 (12.1k) | 1.0 (3.5k) |
| jellyfin `DynamicHlsHelper.GetOutputVideoCodecProfile` | plain | 10 | 14 | 0.64 | 0.90 |  | 9.5 | 6.5 | $0.111 | 7.5 (16.0k) | 1.0 (2.1k) | 0 |
|  | devkb | 10 | 10 | 0.95 | 1.00 |  | 4.0 | 4.0 | $0.056 | 1.0 (0.2k) | 0 | 1.0 (3.5k) |
| efcore `ModificationCommand.GetTableMapping` | plain | 9 | 43 | 0.17 | 0.83 |  | 15.0 | 10.5 | $0.386 | 12.5 (88.9k) | 1.0 (27.6k) | 0 |
|  | devkb | 9 | 16 | 0.59 | 1.00 |  | 13.5 | 9.5 | $0.147 | 6.0 (17.6k) | 1.5 (3.4k) | 4.0 (4.6k) |
| **All 12 runs** | **plain** |  |  | 0.60 | 0.94 | 0.56 | 12.7 | 9.2 | $0.214 | 9.3 (36.6k) | 2.1 (11.9k) | 0 |
| **All 12 runs** | **devkb** |  |  | 0.80 | 0.98 | 0.77 | 8.7 | 6.7 | $0.116 | 4.2 (10.5k) | 1.1 (3.1k) | 1.4 (4.3k) |
