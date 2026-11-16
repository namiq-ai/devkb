# Does devkb help an agent on C#? Chain questions, scored against the compiler

Exploratory: 6 questions, 5 repositories, 24 runs, one model, one session. The C# counterpart of `bench/exercises/cpp/DEVKB-VALUE.md`.

## Setup

- **Question** (read-only): "List every production method that can reach `F`, directly or indirectly, at any depth, and the test files that exercise it."
- **Truth**: the compiler. `bench/roslyn_truth` (Roslyn's semantic model over each repository restored with the .NET SDK it pins) runs on GitHub's runners (`.github/workflows/cs-truth.yml`); `bench/cs_truth_from_roslyn.py` takes the production methods that reach `F` through statically bound calls. Methods that reach it only through virtual or interface dispatch, and callers in benchmark, sample or snippet code, score neither right nor wrong. Production = not a test, benchmark, sample, snippet or example. Questions were picked from the compiler graph (`bench/cs_pick_from_roslyn.py`) or kept from the text picker (`bench/cs_chain_truth.py`) only where the compiler confirmed production callers.
- **Arms**: `plain` (Read, Glob, Grep, read-only shell; no MCP server) and `devkb` (the same tools plus the MCP server in `lean-pack` mode and the AGENTS.md block `devkb init` writes), graph built by the C# round-3 code. The devkb server was proven connected (a pack call answered) before the runs. Model: Sonnet, both arms; 60-turn and $2 caps.
- **Scoring**: method names in backticks that the compiler knows as production methods, matched to the truth by name (a type named in prose or a test method listed with the tests is neither right nor wrong). Recall is solid; precision is approximate where two methods share a name.

## Result

| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Cost | Grep | File load | devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MediatR `ServiceRegistrar.GetConcreteRequestTypes` | plain | 5 | 8 | 0.67 | 1.00 | 0.12 | 9.5 | 7.5 | $0.115 | 6.5 (9.6k) | 2.0 (16.4k) | 0 |
|  | devkb | 5 | 5 | 1.00 | 1.00 | 1.00 | 4.0 | 4.0 | $0.068 | 1.0 (0.0k) | 0 | 1.0 (8.1k) |
| FluentValidation `ValidationContext.GetFromNonGenericContext` | plain | 9 | 18 | 0.73 | 1.00 | 0.95 | 11.5 | 10.5 | $0.227 | 9.0 (36.1k) | 0.5 (0.5k) | 0 |
|  | devkb | 9 | 12 | 0.86 | 1.00 | 1.00 | 9.0 | 9.0 | $0.142 | 5.0 (17.7k) | 0 | 1.0 (1.1k) |
| Polly `ComponentDisposeHelper.ThrowDisposed` | plain | 10 | 12 | 0.76 | 0.90 | 0.16 | 19.5 | 12.0 | $0.248 | 13.0 (41.3k) | 5.5 (6.4k) | 0 |
|  | devkb | 10 | 8 | 1.00 | 0.80 | 0.14 | 11.5 | 9.0 | $0.155 | 8.0 (22.9k) | 0.5 (0.8k) | 1.0 (2.7k) |
| Polly `CircuitStateController.EnsureNotDisposed` | plain | 9 | 20 | 0.61 | 1.00 | 1.00 | 11.0 | 8.5 | $0.195 | 7.5 (27.8k) | 2.5 (18.6k) | 0 |
|  | devkb | 9 | 10 | 0.95 | 1.00 | 1.00 | 4.5 | 4.5 | $0.065 | 1.5 (1.9k) | 0 | 1.0 (3.9k) |
| jellyfin `DynamicHlsHelper.GetOutputVideoCodecProfile` | plain | 10 | 14 | 0.64 | 0.90 |  | 9.5 | 6.5 | $0.111 | 7.5 (16.0k) | 1.0 (2.1k) | 0 |
|  | devkb | 10 | 10 | 1.00 | 1.00 |  | 3.0 | 3.0 | $0.046 | 0 | 0 | 1.0 (3.5k) |
| efcore `ModificationCommand.GetTableMapping` | plain | 9 | 43 | 0.17 | 0.83 |  | 15.0 | 10.5 | $0.386 | 12.5 (88.9k) | 1.0 (27.6k) | 0 |
|  | devkb | 9 | 15 | 0.61 | 1.00 |  | 8.5 | 7.5 | $0.128 | 3.5 (16.2k) | 1.5 (4.7k) | 1.5 (4.5k) |
| **All 12 runs** | **plain** |  |  | 0.60 | 0.94 | 0.56 | 12.7 | 9.2 | $0.214 | 9.3 (36.6k) | 2.1 (11.9k) | 0 |
| **All 12 runs** | **devkb** |  |  | 0.90 | 0.97 | 0.79 | 6.8 | 6.2 | $0.101 | 3.2 (9.8k) | 0.3 (0.9k) | 1.1 (4.0k) |

Calls per run (mean); parentheses give the text returned to the model. Grep = the Grep tool or a shell grep, file load = Read or shell cat/sed/head. Truth is the number of exact production callers; Listed is how many methods the agent named.

Per run:

| Repo | Question | Arm | Run | Turns | Model calls | Cost | Precision | Recall | Wrong names | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| MediatR | GetConcreteRequestTypes | plain | r1 | 9 | 7 | $0.136 | 0.71 | 1.00 | GenerateCombinations, RegisterGenericHandlers |  |
| MediatR | GetConcreteRequestTypes | plain | r2 | 10 | 8 | $0.095 | 0.62 | 1.00 | GenerateCombinations, RegisterGenericHandlers, SetGenericRequestHandlerRegistrationLimitations |  |
| MediatR | GetConcreteRequestTypes | devkb | r1 | 4 | 4 | $0.090 | 1.00 | 1.00 |  |  |
| MediatR | GetConcreteRequestTypes | devkb | r2 | 4 | 4 | $0.047 | 1.00 | 1.00 |  |  |
| FluentValidation | GetFromNonGenericContext | plain | r1 | 11 | 9 | $0.208 | 0.89 | 1.00 | Otherwise |  |
| FluentValidation | GetFromNonGenericContext | plain | r2 | 12 | 12 | $0.247 | 0.57 | 1.00 | Expression, Include, InvokeAsyncCondition, InvokeCondition |  |
| FluentValidation | GetFromNonGenericContext | devkb | r1 | 10 | 10 | $0.176 | 0.73 | 1.00 | ChildRules, ParentContext, SetValidator |  |
| FluentValidation | GetFromNonGenericContext | devkb | r2 | 8 | 8 | $0.109 | 1.00 | 1.00 |  |  |
| Polly | ThrowDisposed | plain | r1 | 20 | 11 | $0.283 | 0.80 | 0.80 | DisposeAsync, ForceDisposeAsync | Implementation, ImplementationAsync |
| Polly | ThrowDisposed | plain | r2 | 19 | 13 | $0.212 | 0.71 | 1.00 | DisposeAsync, DisposeHelper, ExecuteCore, Pipeline |  |
| Polly | ThrowDisposed | devkb | r1 | 11 | 8 | $0.162 | 1.00 | 0.80 |  | Implementation, ImplementationAsync |
| Polly | ThrowDisposed | devkb | r2 | 12 | 10 | $0.148 | 1.00 | 0.80 |  | Implementation, ImplementationAsync |
| Polly | EnsureNotDisposed | plain | r1 | 11 | 8 | $0.206 | 0.53 | 1.00 | AddCircuitBreaker, AddPipeline, CloseAsync, CloseCircuit_NeedsLock |  |
| Polly | EnsureNotDisposed | plain | r2 | 11 | 9 | $0.184 | 0.69 | 1.00 | CloseAsync, Dispose, Initialize, IsolateAsync |  |
| Polly | EnsureNotDisposed | devkb | r1 | 5 | 5 | $0.093 | 1.00 | 1.00 |  |  |
| Polly | EnsureNotDisposed | devkb | r2 | 4 | 4 | $0.037 | 0.90 | 1.00 | Initialize |  |
| jellyfin | GetOutputVideoCodecProfile | plain | r1 | 9 | 6 | $0.130 | 0.64 | 0.90 | AppendDoviPlaylist, GetDolbyVisionHevcCodecTag, GetSegmentLengthsInternal, GetVttTimestampMapMpegts | AppendHdr10PlusString |
| jellyfin | GetOutputVideoCodecProfile | plain | r2 | 10 | 7 | $0.092 | 0.64 | 0.90 | AppendDoviPlaylist, GetDoviString, GetLiveHlsStream, GetVttTimestampMapMpegts | AppendHdr10PlusString |
| jellyfin | GetOutputVideoCodecProfile | devkb | r1 | 3 | 3 | $0.068 | 1.00 | 1.00 |  |  |
| jellyfin | GetOutputVideoCodecProfile | devkb | r2 | 3 | 3 | $0.025 | 1.00 | 1.00 |  |  |
| efcore | GetTableMapping | plain | r1 | 17 | 12 | $0.376 | 0.14 | 0.67 | AddEntry, AddParameters, AddSeedData, AddUnchangedSharingEntries | HandleJson, HandleNonJson, HandleSharedColumns |
| efcore | GetTableMapping | plain | r2 | 13 | 9 | $0.396 | 0.20 | 1.00 | Accessors, AddCommand, AddEntry, AddParameters |  |
| efcore | GetTableMapping | devkb | r1 | 10 | 9 | $0.167 | 0.53 | 1.00 | AddEntry, CreateCommandBatches, CreateModificationCommands, ModificationCommandComparer |  |
| efcore | GetTableMapping | devkb | r2 | 7 | 6 | $0.088 | 0.69 | 1.00 | AddEntry, CreateCommandBatches, ModificationCommandComparer, UpdateSqlGenerator |  |

All plain runs against all devkb runs: median cost $0.207 against $0.091 (-56%).

