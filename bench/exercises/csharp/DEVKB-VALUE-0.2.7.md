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

**Correction (after #47).** The first version of this report said devkb's precision fell to 0.82 and criterion 6 was
not met. That was the benchmark's truth, not the agent. The compiler truth (`bench/roslyn_truth`) recorded calls only:
EF Core's target is reached through four properties, so methods that reach it by reading them were scored wrong. It
also merged two classes that Polly and Polly.Core both declare (`Polly.CircuitBreaker.CircuitStateController<T>`): ids
were not qualified by assembly. Both are fixed in the tool; the truth was regenerated on GitHub's runners (`cs-truth`
run 44015588074; definitions and call edges otherwise identical to the run behind the first version) and the same
transcripts rescored (`bench/cs_value_rescore.py`; `truth-corrections.md` has the hand check that found it).

| All 12 runs | Precision, old truth (first published) | **Precision, fixed compiler truth** | Recall, fixed | Precision, + hand-neutral names | Test files | Turns | Median cost vs plain |
|---|---|---|---|---|---|---|---|
| plain agent (reused) | 0.60 | 0.71 | 0.92 | 0.77 | 0.56 | 12.7 | $0.207 |
| 0.2.6 (`DEVKB-VALUE.md`) | 0.85 | 0.94 | 0.91 | 0.98 | 0.66 | 7.6 | −40% |
| **0.2.7, default tools** | 0.82 | **0.93** | **0.90** | **0.98** | 0.75 | 8.8 | **−53%** |
| 0.2.7, read tools denied | 0.80 | 0.86 | 0.94 | 0.92 | 0.77 | 8.7 | −42% |

"Hand-neutral names" (`uncertain_by_hand` in `questions.json`) are six names the tool still cannot judge, scored
neither right nor wrong: Polly's `CloseAsync`, `IsolateAsync`, `Initialize` (they invoke callbacks that reach the
target), `DisposeHelper` (a property, not a method), EF Core's `ModificationCommandComparer`, `UpdateSqlGenerator`
(type names) and `IsValid` (in EFCore.SqlServer, which the truth job does not compile; it reaches the target through
the interface). Test-file, turn and cost columns are unchanged from the first version.

Per question, devkb-arm precision on the fixed compiler truth (old truth in brackets), and recall on the fixed truth:

| Question | Truth (old → fixed) | 0.2.6 | 0.2.7 | 0.2.7, read tools denied | Recall 0.2.6 / 0.2.7 |
|---|---|---|---|---|---|
| MediatR `ServiceRegistrar.GetConcreteRequestTypes` | 5 → 5 | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) | 1.00 / 1.00 |
| FluentValidation `ValidationContext.GetFromNonGenericContext` | 9 → 9 | 0.88 (0.88) | 0.90 (0.90) | 0.86 (0.86) | 0.94 / 1.00 |
| Polly `ComponentDisposeHelper.ThrowDisposed` | 10 → 10 | 0.89 (0.89) | 0.88 (0.88) | 0.72 (0.72) | 0.80 / 0.75 |
| Polly `CircuitStateController.EnsureNotDisposed` | 9 → 12 | 0.91 (0.91) | 0.86 (0.86) | 0.74 (0.69) | 0.75 / 0.75 |
| Jellyfin `DynamicHlsHelper.GetOutputVideoCodecProfile` | 10 → 10 | 1.00 (1.00) | 1.00 (1.00) | 0.95 (0.95) | 1.00 / 1.00 |
| EF Core `ModificationCommand.GetTableMapping` | 9 → 14 | 0.94 (0.45) | 0.93 (0.25) | 0.90 (0.59) | 1.00 / 0.93 |

## What this shows, and what it does not

- **Criterion 6 of #40: precision met, recall not.** On the fixed compiler truth devkb 0.2.7's precision is 0.93
  (≥ 0.85); its recall is 0.90 against the ≥ 0.96 asked. The criterion was written against the old truth, on which
  recall was 0.96; the fixed truth is larger, and 0.2.6 scores the same on it (0.91).
- **There was no precision drop.** 0.2.6 0.94, 0.2.7 0.93 on the fixed truth: one name across 12 runs. The old
  truth's 0.85 → 0.82 came from EF Core alone, where it punished the long answers (33–39 names) for naming methods
  that read `ColumnModifications`; corrected, EF Core is 0.94 and 0.93.
- **Where recall is lost.** Polly `EnsureNotDisposed`: the fixed truth adds the strategy's constructor,
  `CreateStrategy` and `AddCircuitBreaker`, because the constructor reads `CircuitState` inside a lambda
  (`stateProvider?.Initialize(() => _controller.CircuitState)`) and the truth credits a lambda's calls to the member
  that creates it (the convention devkb's graph uses too); no agent run names them. Polly `ThrowDisposed`:
  `Implementation`/`ImplementationAsync`, missed by every run since the 0.2.6 report.
- **The read tools help.** Denied, precision is 0.86 against 0.93 (recall 0.94 against 0.90); most of the difference
  is the Polly runs without them naming dispose methods that do not reach the target.
- **Where the C# round reached these questions.** The first pack answer, compared run by run with 0.2.6's: on
  FluentValidation it now resolves 12 symbols where 0.2.6 resolved 1 (`ValidationContext<T>.GetFromNonGenericContext`
  is a static call on a generic type, round 4's F6, the miss that motivated it); on MediatR, Polly `EnsureNotDisposed`,
  Jellyfin and EF Core it is identical; in both Polly `ThrowDisposed` runs the agent asked `callers` instead.
- **Limits.** 2 runs per question. Methods reaching a target only through interface dispatch or a registered callback
  are neither right nor wrong (as before); the EF Core truth job compiles EFCore.Relational only.
- Two devkb limitations the runs exposed are in `docs/specs/csharp-4-dogfood-log.md` (D8: EF Core's fixture copies
  under `eng/**/fixtures/` make `callers CommandBatchPreparer.BatchCommands` ambiguous; D9: the EF Core exploration,
  which found the real callers).

## Result, 0.2.7 with the default tools (old compiler truth, as first published)

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

## Result, 0.2.7 with the read tools denied (old compiler truth)

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
